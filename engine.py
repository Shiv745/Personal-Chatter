"""PulseAI Unified Automation Engine (Concurrent WhatsApp + Instagram + LinkedIn)."""
import asyncio
import uuid
from typing import Any, Dict, List, Optional

import config_manager
import database as db
from brain import ChatBrain
from human_typing import HourlyRateLimiter
from platforms.browser_manager import BrowserManager
from platforms.instagram_bot import InstagramBot
from platforms.linkedin_bot import LinkedInBot
from platforms.whatsapp_bot import WhatsAppBot
from scanners import scan_instagram_profile, scan_linkedin_profile


class AgentEngine:
    def __init__(self) -> None:
        db.init_db()
        self.cfg = config_manager.load_config()
        self.brain = ChatBrain()
        self.browser = BrowserManager()
        self.rate_limiter = HourlyRateLimiter()

        self.mode: str = self.cfg.get("default_mode", "autopilot")
        self.running: bool = False
        self.paused: bool = False
        self._tasks: List[asyncio.Task] = []
        self._msg_counters: Dict[int, int] = {}

        self.status_text: Dict[str, str] = {
            "instagram": "Browser offline — click Start Engine",
            "whatsapp": "Browser offline — click Start Engine",
            "linkedin": "Browser offline — click Start Engine",
        }

        self.pending_approvals: Dict[str, Dict[str, Any]] = {}
        self.copilot_suggestions: Dict[int, Dict[str, Any]] = {}

        self.bots = {
            "whatsapp": WhatsAppBot(self),
            "instagram": InstagramBot(self),
            "linkedin": LinkedInBot(self),
        }

        self._seed_demo_contacts_if_empty()

    def _seed_demo_contacts_if_empty(self) -> None:
        if db.list_contacts():
            return
        cid_ig = db.upsert_contact(
            "sneha_demo",
            "instagram",
            name="Sneha (Demo)",
            persona="personal",
            stage="flirty",
            chat_style="Playful teasing, sharp witty Hinglish humour, confident & fun",
            chat_target="Ask her out for a weekend coffee date",
        )
        db.save_profile_intel(
            cid_ig,
            bio_summary="Exploring cafes & chaos | Law student",
            fav_songs="Apna Bana Le, Kesariya, Arijit Singh",
            hobbies="Photography, Cafe hopping, Late-night drives",
            likes="Cold brew, Sarcasm, Street food",
            vibe_notes="Loves playful banter and quick comebacks.",
        )
        db.add_memory_fact(cid_ig, "inside_joke", "Still owes you a cold coffee bet")
        db.add_message(cid_ig, "her", "Hey! Did you check out that new cafe we talked about?")

        cid_wa = db.upsert_contact(
            "Aanya (Demo)",
            "whatsapp",
            name="Aanya (Demo)",
            persona="personal",
            stage="romantic",
            chat_style="Warm, romantic, light teasing, genuine & heartfelt Hinglish",
            chat_target="Say I love you naturally at the right moment",
        )
        db.save_profile_intel(
            cid_wa,
            bio_summary="Music lover & weekend traveller",
            fav_songs="Tum Hi Ho, Coldplay - Yellow",
            hobbies="Travel, Sketching",
            likes="Chai, Road trips, Dry humour",
        )
        db.add_memory_fact(cid_wa, "inside_joke", "The samosa incident at Rajiv Chowk")
        db.add_message(cid_wa, "her", "Kal shaam free ho kya? Chai pe chalein?")

        cid_li = db.upsert_contact(
            "ankit-sharma-demo",
            "linkedin",
            name="Ankit Sharma (Demo)",
            persona="professional",
            stage="casual",
            chat_style="Crisp, confident, polite & sharp tech professional",
            chat_target="Schedule a 15-minute intro call for Azure DevOps role",
        )
        db.save_profile_intel(
            cid_li,
            role_company="Talent Acquisition @ TechCorp",
            bio_summary="Hiring Cloud, Azure & DevOps engineers across India.",
            skills="Azure DevOps, Kubernetes, Terraform, Cloud Hiring",
            recent_activity="DevOps Hiring, Kubernetes Best Practices",
            conversation_goal="Explore Azure DevOps role & schedule a quick intro call",
        )
        db.add_message(cid_li, "her", "Hi Shivendra, came across your Azure & DevOps profile. Are you open to exploring new roles?")

    def set_status(self, platform: str, text: str) -> None:
        self.status_text[platform] = text

    def set_mode(self, mode: str) -> None:
        if mode in {"autopilot", "hybrid", "copilot"}:
            self.mode = mode
            db.log_event("system", f"Mode switched to {mode.upper()}")

    async def start_engine(self) -> None:
        if self.running:
            self.paused = False
            db.log_event("system", "Engine resumed.")
            return

        self.running = True
        self.paused = False
        await self.browser.start()

        enabled = config_manager.load_config().get("enabled_platforms", {})
        self._tasks = []
        for platform, bot in self.bots.items():
            if enabled.get(platform, True):
                self._tasks.append(asyncio.create_task(bot.run_loop()))

        db.log_event("system", "All enabled platform engines running concurrently!")

    async def pause_engine(self) -> None:
        self.paused = True
        for p in self.status_text:
            if self.browser.is_open:
                self.status_text[p] = "Paused by user"
        db.log_event("system", "Engine paused.")

    async def stop_engine(self) -> None:
        self.running = False
        self.paused = False
        for t in self._tasks:
            t.cancel()
        self._tasks.clear()
        await self.browser.stop()
        for p in self.status_text:
            self.status_text[p] = "Stopped"

    async def handle_incoming_message(
        self,
        contact_id: int,
        incoming_text: str,
        simulate_only: bool = False,
        force_propose: bool = False,
        target_override: str = "",
    ) -> Dict[str, Any]:
        ctx = db.get_full_context(contact_id)
        if not ctx:
            raise ValueError("Contact not found")

        contact = ctx["contact"]
        platform = contact["platform"]

        if not force_propose and incoming_text.strip():
            db.add_message(contact_id, "her", incoming_text)

        active_target = (target_override or contact.get("chat_target") or "").strip()
        trigger_prompt = (
            f"(Smoothly execute target right now: {active_target or 'Propose / ask out warmly'})"
            if force_propose
            else incoming_text
        )

        result = await asyncio.to_thread(
            self.brain.generate_reply,
            contact_id,
            trigger_prompt,
            self.mode if not force_propose else "autopilot",
            force_propose,
            active_target,
        )

        if self.mode == "copilot" and not force_propose:
            self.copilot_suggestions[contact_id] = result
            db.log_event(platform, f"Co-pilot generated 3 options for {contact['name']}.")
            return {"status": "copilot_ready", "suggestions": result}

        bubbles: List[str] = result.get("bubbles") or []
        if platform == "whatsapp" and bubbles:
            combined = " ".join(bubble.strip() for bubble in bubbles if bubble.strip())
            bubbles = [combined] if combined else []
        mood = result.get("mood_detected", "")

        if self.mode == "hybrid" and (result.get("needs_approval") or force_propose):
            approval_id = str(uuid.uuid4())[:8]
            self.pending_approvals[approval_id] = {
                "id": approval_id,
                "contact_id": contact_id,
                "platform": platform,
                "contact_name": contact["name"],
                "handle": contact["handle"],
                "bubbles": bubbles,
                "reason": result.get("approval_reason") or (f"Target trigger: {active_target}" if force_propose else "Needs review"),
                "simulate_only": simulate_only,
                "mood": mood,
            }
            db.log_event(platform, f"Hybrid pause for {contact['name']}: {self.pending_approvals[approval_id]['reason']}", level="warn")
            return {"status": "awaiting_approval", "approval": self.pending_approvals[approval_id]}

        await self._deliver_bubbles(
            contact=contact,
            bubbles=bubbles,
            mood=mood,
            simulate_only=simulate_only,
        )

        db.update_stage_warmth(
            contact_id,
            stage=result.get("suggested_stage"),
            warmth_delta=int(result.get("warmth_delta", 0)),
        )

        self._msg_counters[contact_id] = self._msg_counters.get(contact_id, 0) + 1
        if self._msg_counters[contact_id] % 3 == 0:
            asyncio.create_task(asyncio.to_thread(self.brain.extract_and_save_memories, contact_id))

        return {"status": "sent", "bubbles": bubbles, "meta": result}

    async def _deliver_bubbles(
        self,
        contact: Dict[str, Any],
        bubbles: List[str],
        mood: str = "",
        simulate_only: bool = False,
    ) -> None:
        platform = contact["platform"]
        handle = contact["name"] if platform == "linkedin" and contact.get("name") else contact["handle"]

        if not simulate_only:
            if not self.browser.is_open:
                raise RuntimeError("Browser is not open; message was not sent.")
            bot = self.bots.get(platform)
            if not bot:
                raise RuntimeError(f"No sender is configured for {platform}.")
            sent = await bot.send_bubbles_to_contact(handle, bubbles)
            if not sent:
                raise RuntimeError(f"Failed to send message to {handle}.")

        for b in bubbles:
            if b.strip():
                db.add_message(contact["id"], "me", b.strip(), mood=mood)

    async def approve_pending(self, approval_id: str, edited_bubbles: Optional[List[str]] = None) -> bool:
        item = self.pending_approvals.pop(approval_id, None)
        if not item:
            return False
        ctx = db.get_full_context(item["contact_id"])
        if not ctx:
            return False
        bubbles = edited_bubbles if edited_bubbles else item["bubbles"]
        await self._deliver_bubbles(
            ctx["contact"], bubbles, mood=item.get("mood", ""), simulate_only=item.get("simulate_only", False)
        )
        db.log_event(item["platform"], f"Approved & sent reply to {item['contact_name']}")
        return True

    def reject_pending(self, approval_id: str) -> bool:
        return self.pending_approvals.pop(approval_id, None) is not None

    async def send_manual_or_copilot(
        self, contact_id: int, bubbles: List[str], simulate_only: bool = False
    ) -> bool:
        ctx = db.get_full_context(contact_id)
        if not ctx:
            return False
        self.copilot_suggestions.pop(contact_id, None)
        await self._deliver_bubbles(ctx["contact"], bubbles, simulate_only=simulate_only)
        return True

    async def trigger_profile_scan(self, contact_id: int) -> Dict[str, Any]:
        ctx = db.get_full_context(contact_id)
        if not ctx:
            raise ValueError("Contact not found")
        contact = ctx["contact"]
        platform = contact["platform"]

        if not self.browser.is_open:
            await self.browser.start()

        page = await self.browser.get_page(platform)
        if not page:
            raise RuntimeError(f"{platform.title()} browser tab is not available.")

        async with self.browser.typing_lock:
            await page.bring_to_front()
            if platform == "instagram":
                intel = await scan_instagram_profile(page, self.brain, contact_id, contact["handle"])
                return intel
            if platform == "linkedin":
                target = contact.get("profile_url") or contact["handle"]
                intel = await scan_linkedin_profile(page, self.brain, contact_id, target)
                return intel
            raise ValueError("Profile scanning is supported for Instagram and LinkedIn.")

    def get_dashboard_state(self) -> Dict[str, Any]:
        cfg = config_manager.load_config()
        caps = {}
        for p in ("instagram", "whatsapp", "linkedin"):
            caps[p] = {
                "used": self.rate_limiter.count_last_hour(p),
                "max": cfg["delays"][p]["max_replies_per_hour"],
                "poll": f"{cfg['delays'][p]['poll_min_sec']}-{cfg['delays'][p]['poll_max_sec']}s",
                "type_speed": f"{(cfg['delays'][p]['type_min_ms'] + cfg['delays'][p]['type_max_ms']) // 2}ms/char",
                "status": self.status_text.get(p, "Idle"),
            }
        return {
            "mode": self.mode,
            "running": self.running,
            "paused": self.paused,
            "browser_open": self.browser.is_open,
            "gemini_connected": self.brain.is_connected(),
            "primary_model": self.brain.primary_model,
            "propose_model": self.brain.propose_model,
            "platforms": caps,
            "pending_approvals": list(self.pending_approvals.values()),
            "logs": db.get_logs(40),
        }
