"""Local HTTP API server connecting the PyWebView Desktop UI to AgentEngine."""
from pathlib import Path
from aiohttp import web

import config_manager
import database as db
from engine import AgentEngine

UI_DIR = Path(__file__).parent / "ui"


def create_app(engine: AgentEngine) -> web.Application:
    app = web.Application()

    async def index(_request):
        return web.FileResponse(UI_DIR / "index.html")

    async def api_state(_request):
        return web.json_response(engine.get_dashboard_state())

    async def api_mode(request):
        body = await request.json()
        engine.set_mode(body.get("mode", "autopilot"))
        return web.json_response({"ok": True, "mode": engine.mode})

    async def api_engine_control(request):
        action = request.match_info["action"]
        try:
            if action == "start":
                await engine.start_engine()
            elif action == "pause":
                await engine.pause_engine()
            elif action == "stop":
                await engine.stop_engine()
            else:
                return web.json_response({"error": "Invalid action"}, status=400)
            return web.json_response({"ok": True, "state": engine.get_dashboard_state()})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def api_contacts_list(request):
        platform = request.query.get("platform")
        contacts = db.list_contacts(platform=platform)
        return web.json_response({"contacts": contacts})

    async def api_contacts_add(request):
        body = await request.json()
        handle = (body.get("handle") or "").strip()
        platform = (body.get("platform") or "instagram").strip().lower()
        name = (body.get("name") or handle).strip()
        profile_url = (body.get("profile_url") or "").strip()
        persona = body.get("persona")
        chat_style = (body.get("chat_style") or "").strip()
        chat_target = (body.get("chat_target") or "").strip()
        if not handle:
            return web.json_response({"error": "Handle / Contact name is required"}, status=400)
        cid = db.upsert_contact(
            handle=handle,
            platform=platform,
            name=name,
            profile_url=profile_url,
            persona=persona,
            chat_style=chat_style,
            chat_target=chat_target,
        )
        db.log_event(platform, f"Added '{name}' to whitelist (Target: {chat_target or 'Default'}).")
        return web.json_response({"ok": True, "contact_id": cid})

    async def api_contact_detail(request):
        cid = int(request.match_info["id"])
        ctx = db.get_full_context(cid)
        if not ctx:
            return web.json_response({"error": "Not found"}, status=404)
        ctx["copilot"] = engine.copilot_suggestions.get(cid)
        return web.json_response(ctx)

    async def api_contact_update(request):
        cid = int(request.match_info["id"])
        body = await request.json()
        db.update_contact_settings(
            cid,
            persona=body.get("persona"),
            stage=body.get("stage"),
            warmth_score=body.get("warmth_score"),
            whitelisted=body.get("whitelisted"),
            name=body.get("name"),
            profile_url=body.get("profile_url"),
            chat_style=body.get("chat_style"),
            chat_target=body.get("chat_target"),
        )
        if "profile_intel" in body and isinstance(body["profile_intel"], dict):
            db.overwrite_profile_intel(cid, body["profile_intel"])
        return web.json_response({"ok": True})

    async def api_contact_delete(request):
        cid = int(request.match_info["id"])
        db.delete_contact(cid)
        return web.json_response({"ok": True})

    async def api_add_fact(request):
        cid = int(request.match_info["id"])
        body = await request.json()
        db.add_memory_fact(cid, body.get("category", "personal"), body.get("fact", ""))
        return web.json_response({"ok": True})

    async def api_delete_fact(request):
        fid = int(request.match_info["fid"])
        db.delete_memory_fact(fid)
        return web.json_response({"ok": True})

    async def api_simulate_incoming(request):
        cid = int(request.match_info["id"])
        body = await request.json()
        text = (body.get("text") or "").strip()
        if not text:
            return web.json_response({"error": "Empty message"}, status=400)
        try:
            res = await engine.handle_incoming_message(cid, text, simulate_only=True)
            return web.json_response({"ok": True, "result": res})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def api_propose(request):
        cid = int(request.match_info["id"])
        body = await request.json() if request.can_read_body else {}
        simulate = bool(body.get("simulate_only", not engine.browser.is_open))
        target_override = (body.get("target_override") or "").strip()
        try:
            res = await engine.handle_incoming_message(
                cid,
                "",
                simulate_only=simulate,
                force_propose=True,
                target_override=target_override,
            )
            return web.json_response({"ok": True, "result": res})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def api_send_manual(request):
        cid = int(request.match_info["id"])
        body = await request.json()
        bubbles = body.get("bubbles")
        if not bubbles:
            txt = (body.get("text") or "").strip()
            bubbles = [txt] if txt else []
        if not bubbles:
            return web.json_response({"error": "Empty text"}, status=400)
        simulate = bool(body.get("simulate_only", not engine.browser.is_open))
        await engine.send_manual_or_copilot(cid, bubbles, simulate_only=simulate)
        return web.json_response({"ok": True})

    async def api_scan_profile(request):
        cid = int(request.match_info["id"])
        try:
            intel = await engine.trigger_profile_scan(cid)
            return web.json_response({"ok": True, "intel": intel})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def api_approval_action(request):
        aid = request.match_info["aid"]
        body = await request.json()
        action = body.get("action")
        if action == "approve":
            edited = body.get("bubbles")
            ok = await engine.approve_pending(aid, edited_bubbles=edited)
            return web.json_response({"ok": ok})
        ok = engine.reject_pending(aid)
        return web.json_response({"ok": ok})

    async def api_config_get(_request):
        return web.json_response(config_manager.load_config())

    async def api_config_save(request):
        body = await request.json()
        current = config_manager.load_config()
        merged = config_manager._deep_merge(current, body)
        config_manager.save_config(merged)
        connected = engine.brain.reload_client()
        db.log_event("system", f"Settings saved. Gemini connected: {connected}")
        return web.json_response({"ok": True, "gemini_connected": connected})

    async def api_db_export(_request):
        return web.json_response(db.export_all_data())

    app.router.add_get("/", index)
    app.router.add_static("/ui", UI_DIR)
    app.router.add_get("/api/state", api_state)
    app.router.add_post("/api/mode", api_mode)
    app.router.add_post("/api/engine/{action}", api_engine_control)
    app.router.add_get("/api/contacts", api_contacts_list)
    app.router.add_post("/api/contacts", api_contacts_add)
    app.router.add_get("/api/contacts/{id}", api_contact_detail)
    app.router.add_put("/api/contacts/{id}", api_contact_update)
    app.router.add_delete("/api/contacts/{id}", api_contact_delete)
    app.router.add_post("/api/contacts/{id}/facts", api_add_fact)
    app.router.add_delete("/api/facts/{fid}", api_delete_fact)
    app.router.add_post("/api/contacts/{id}/simulate", api_simulate_incoming)
    app.router.add_post("/api/contacts/{id}/propose", api_propose)
    app.router.add_post("/api/contacts/{id}/send", api_send_manual)
    app.router.add_post("/api/contacts/{id}/scan", api_scan_profile)
    app.router.add_post("/api/approvals/{aid}", api_approval_action)
    app.router.add_get("/api/config", api_config_get)
    app.router.add_post("/api/config", api_config_save)
    app.router.add_get("/api/export", api_db_export)

    return app
