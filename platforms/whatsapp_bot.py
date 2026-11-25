"""WhatsApp Web Playwright Automation Worker."""
import asyncio
import time
from typing import Dict, List, Optional, Tuple

import config_manager
import database as db
from human_typing import human_read_delay, random_poll_sleep, send_multi_bubbles


class WhatsAppBot:
    INCOMING_QUIET_SEC = 6.0

    def __init__(self, engine) -> None:
        self.engine = engine
        self.platform = "whatsapp"
        self._last_seen: Dict[str, str] = {}
        self._pending_incoming: Dict[str, Tuple[str, str, float]] = {}

    async def send_bubbles_to_contact(self, handle: str, bubbles: List[str]) -> bool:
        page = await self.engine.browser.get_page(self.platform)
        if not page:
            return False

        cfg = config_manager.load_config()["delays"][self.platform]
        async with self.engine.browser.typing_lock:
            try:
                await page.bring_to_front()
                if not await self._open_chat(page, handle):
                    db.log_event(self.platform, f"Could not locate WhatsApp chat for '{handle}'", level="warn")
                    return False

                input_box = page.locator("footer div[contenteditable='true'][role='textbox']").last
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
                self.engine.set_status(self.platform, "Idle (monitoring)")
                return True
            except Exception as e:
                db.log_event(self.platform, f"Send error for {handle}: {e}", level="error")
                self.engine.set_status(self.platform, "Idle")
                return False

    async def _open_chat(self, page, contact_name: str) -> bool:
        # Try clicking chat directly in left pane first
        chat_span = page.locator(f"span[title='{contact_name}']").first
        if await chat_span.count() > 0:
            await chat_span.click()
            await asyncio.sleep(0.2)
            return True

        # Fallback: search box
        search = page.locator("div[contenteditable='true'][data-tab='3']").first
        if await search.count() > 0:
            await search.click()
            await page.keyboard.press("Control+A")
            await page.keyboard.press("Backspace")
            await page.keyboard.type(contact_name, delay=10)
            await asyncio.sleep(0.2)
            found = page.locator(f"span[title='{contact_name}']").first
            if await found.count() > 0:
                await found.click()
                await asyncio.sleep(0.2)
                return True
        return False

    async def _read_latest_incoming(self, page) -> Optional[str]:
        incoming = page.locator("div.message-in span.selectable-text")
        count = await incoming.count()
        if count == 0:
            return None
        text = (await incoming.nth(count - 1).inner_text()).strip()
        return text or None

    async def run_loop(self) -> None:
        db.log_event(self.platform, "WhatsApp monitor started.")
        while self.engine.running:
            cfg_all = config_manager.load_config()
            d_cfg = cfg_all["delays"][self.platform]

            if self.engine.paused or not self.engine.browser.is_open:
                await asyncio.sleep(2.0)
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
                        if not await self._open_chat(page, handle):
                            continue
                        latest = await self._read_latest_incoming(page)

                    if not latest:
                        continue

                    prev = self._last_seen.get(handle)
                    if prev is None:
                        # Seed initial latest message so we don't reply to old history on startup
                        self._last_seen[handle] = latest
                        self._pending_incoming.pop(handle, None)
                        continue
                    if latest == prev:
                        self._pending_incoming.pop(handle, None)
                        continue

                    pending = self._pending_incoming.get(handle)
                    now = time.monotonic()
                    if pending is None:
                        self._pending_incoming[handle] = (latest, latest, now)
                        continue

                    pending_text, pending_latest, observed_at = pending
                    if pending_latest != latest:
                        self._pending_incoming[handle] = (
                            f"{pending_text}\n{latest}",
                            latest,
                            now,
                        )
                        continue

                    if now - observed_at < self.INCOMING_QUIET_SEC:
                        continue

                    incoming_text = pending_text
                    self._last_seen[handle] = latest
                    self._pending_incoming.pop(handle, None)
                    db.log_event(
                        self.platform,
                        f"New message from {contact['name']}: {incoming_text[:60]}",
                    )

                    if d_cfg["read_max_sec"] > 0:
                        await human_read_delay(
                            incoming_text,
                            d_cfg["read_min_sec"],
                            d_cfg["read_max_sec"],
                            status_cb=lambda s: self.engine.set_status(self.platform, s),
                        )
                    await self.engine.handle_incoming_message(contact["id"], incoming_text)

                except Exception as e:
                    db.log_event(self.platform, f"Poll warning ({handle}): {e}", level="warn")

            sleep_s = max(0.3, random_poll_sleep(d_cfg["poll_min_sec"], d_cfg["poll_max_sec"]))
            self.engine.set_status(self.platform, f"Next check in {sleep_s:.0f}s")
            await asyncio.sleep(sleep_s)
