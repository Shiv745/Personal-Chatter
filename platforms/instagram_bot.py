"""Instagram DM Playwright Automation Worker with Anti-Ban Guardrails."""
import asyncio
from typing import Dict, List, Optional

import config_manager
import database as db
from human_typing import human_read_delay, random_poll_sleep, send_multi_bubbles


class InstagramBot:
    def __init__(self, engine) -> None:
        self.engine = engine
        self.platform = "instagram"
        self._last_seen: Dict[str, str] = {}

    async def _check_safety_warning(self, page) -> bool:
        """Detects Instagram challenge / checkpoint / automated behavior warning and auto-pauses."""
        url = page.url.lower()
        if any(k in url for k in ("challenge", "checkpoint", "suspended", "accounts/login")):
            db.log_event(self.platform, "Instagram login/security screen detected! Auto-pausing.", level="warn")
            self.engine.set_status(self.platform, "PAUSED: Security check / Login needed")
            return True
        try:
            body_snippet = (await page.inner_text("body"))[:600].lower()
            if "suspect automated behavior" in body_snippet or "try again later" in body_snippet:
                db.log_event(self.platform, "Instagram rate-limit popup detected! Auto-pausing.", level="error")
                self.engine.paused = True
                self.engine.set_status(self.platform, "AUTO-PAUSED: Safety Guard triggered")
                return True
        except Exception:
            pass
        return False

    async def _open_dm_thread(self, page, handle: str) -> bool:
        clean = handle.lstrip("@").strip()
        if "/direct/inbox" not in page.url and "/direct/t/" not in page.url:
            await page.goto("https://www.instagram.com/direct/inbox/", wait_until="domcontentloaded", timeout=35000)
            await asyncio.sleep(2.5)

        # Look for thread in inbox list matching handle or display name
        thread = page.locator(f"div[role='listitem']:has-text('{clean}'), span:text-is('{clean}')").first
        if await thread.count() > 0:
            await thread.click()
            await asyncio.sleep(1.5)
            return True
        return False

    async def _read_latest_message(self, page) -> Optional[str]:
        # Instagram DM message text nodes inside the conversation pane
        msgs = page.locator("div[role='grid'] div[dir='auto']")
        count = await msgs.count()
        if count == 0:
            return None
        # Check last few text nodes to skip timestamps
        for idx in range(count - 1, max(-1, count - 6), -1):
            txt = (await msgs.nth(idx).inner_text()).strip()
            if txt and len(txt) > 0 and not txt.lower().startswith("seen"):
                return txt
        return None

    async def send_bubbles_to_contact(self, handle: str, bubbles: List[str]) -> bool:
        page = await self.engine.browser.get_page(self.platform)
        if not page:
            return False

        cfg = config_manager.load_config()["delays"][self.platform]
        async with self.engine.browser.typing_lock:
            try:
                await page.bring_to_front()
                if await self._check_safety_warning(page):
                    return False

                if not await self._open_dm_thread(page, handle):
                    db.log_event(self.platform, f"Could not find Instagram DM thread for @{handle}", level="warn")
                    return False

                input_box = page.locator("div[role='textbox'][contenteditable='true'], textarea[placeholder*='Message']").last
                await input_box.wait_for(state="visible", timeout=8000)

                await send_multi_bubbles(
                    page=page,
                    input_locator=input_box,
                    bubbles=bubbles,
                    type_min_ms=cfg["type_min_ms"],
                    type_max_ms=cfg["type_max_ms"],
                    send_key="Enter",
                    status_cb=lambda s: self.engine.set_status(self.platform, s),
                )
                self.engine.rate_limiter.record_send(self.platform)
                self.engine.set_status(self.platform, "Idle (safe monitoring)")
                return True
            except Exception as e:
                db.log_event(self.platform, f"Send error (@{handle}): {e}", level="error")
                self.engine.set_status(self.platform, "Idle")
                return False

    async def run_loop(self) -> None:
        db.log_event(self.platform, "Instagram monitor started (strict anti-ban pacing).")
        while self.engine.running:
            cfg_all = config_manager.load_config()
            d_cfg = cfg_all["delays"][self.platform]

            if self.engine.paused or not self.engine.browser.is_open:
                await asyncio.sleep(2.5)
                continue

            page = await self.engine.browser.get_page(self.platform)
            if not page:
                await asyncio.sleep(3.0)
                continue

            whitelisted = [
                c for c in db.list_contacts(self.platform) if c.get("whitelisted")
            ]

            for contact in whitelisted:
                if self.engine.paused or not self.engine.running:
                    break

                handle = contact["handle"]
                if not self.engine.rate_limiter.can_send(self.platform, d_cfg["max_replies_per_hour"]):
                    self.engine.set_status(self.platform, "Hourly cap reached — cooling down")
                    break

                try:
                    async with self.engine.browser.typing_lock:
                        await page.bring_to_front()
                        if await self._check_safety_warning(page):
                            break
                        if not await self._open_dm_thread(page, handle):
                            continue
                        latest = await self._read_latest_message(page)

                    if not latest:
                        continue

                    # Ignore if latest text matches our own last sent message
                    last_db = db.get_last_message(contact["id"])
                    if last_db and last_db["sender"] == "me" and last_db["content"].strip() == latest:
                        self._last_seen[handle] = latest
                        continue

                    prev = self._last_seen.get(handle)
                    if prev is None:
                        self._last_seen[handle] = latest
                        continue
                    if latest == prev:
                        continue

                    self._last_seen[handle] = latest
                    db.log_event(self.platform, f"New Insta DM from @{handle}: {latest[:60]}")

                    await human_read_delay(
                        latest,
                        d_cfg["read_min_sec"],
                        d_cfg["read_max_sec"],
                        status_cb=lambda s: self.engine.set_status(self.platform, s),
                    )
                    await self.engine.handle_incoming_message(contact["id"], latest)

                except Exception as e:
                    db.log_event(self.platform, f"Poll notice (@{handle}): {e}", level="warn")

            sleep_s = random_poll_sleep(d_cfg["poll_min_sec"], d_cfg["poll_max_sec"])
            self.engine.set_status(self.platform, f"Anti-ban wait: {sleep_s:.0f}s")
            await asyncio.sleep(sleep_s)
