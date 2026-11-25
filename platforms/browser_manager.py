"""Persistent Chromium/Chrome Manager for Concurrent WhatsApp, Instagram & LinkedIn Tabs."""
import asyncio
from pathlib import Path
from typing import Dict, Optional
from playwright.async_api import async_playwright, BrowserContext, Page, Playwright

import config_manager
import database as db


class BrowserManager:
    def __init__(self) -> None:
        self._pw: Optional[Playwright] = None
        self.context: Optional[BrowserContext] = None
        self.pages: Dict[str, Page] = {}
        # Single typing lock so only one platform types at a time (natural human behavior)
        self.typing_lock = asyncio.Lock()
        self.is_open = False

    async def start(self) -> None:
        if self.is_open and self.context:
            return

        cfg = config_manager.load_config()
        b_cfg = cfg.get("browser", {})
        profile_dir = Path(b_cfg.get("profile_dir", "browser_profile")).resolve()
        profile_dir.mkdir(parents=True, exist_ok=True)
        headless = bool(b_cfg.get("headless", False))
        use_chrome = bool(b_cfg.get("use_installed_chrome", True))

        self._pw = await async_playwright().start()

        launch_kwargs = dict(
            user_data_dir=str(profile_dir),
            headless=headless,
            viewport={"width": 1280, "height": 840},
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
            ],
        )

        # Prefer real installed Chrome on Windows for better anti-detection; fallback to Playwright Chromium
        try:
            if use_chrome:
                self.context = await self._pw.chromium.launch_persistent_context(
                    channel="chrome", **launch_kwargs
                )
            else:
                self.context = await self._pw.chromium.launch_persistent_context(**launch_kwargs)
        except Exception:
            db.log_event("system", "Installed Chrome not found, using Playwright Chromium.", level="info")
            self.context = await self._pw.chromium.launch_persistent_context(**launch_kwargs)

        # Hide navigator.webdriver flag subtly
        await self.context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )

        enabled = cfg.get("enabled_platforms", {})
        urls = {
            "whatsapp": "https://web.whatsapp.com/",
            "instagram": "https://www.instagram.com/direct/inbox/",
            "linkedin": "https://www.linkedin.com/messaging/",
        }

        existing = self.context.pages
        first_used = False
        for platform, url in urls.items():
            if not enabled.get(platform, True):
                continue
            if not first_used and existing:
                page = existing[0]
                first_used = True
            else:
                page = await self.context.new_page()
            self.pages[platform] = page
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=40000)
                db.log_event(platform, f"Opened {platform.title()} tab. Log in once if prompted.")
            except Exception as e:
                db.log_event(platform, f"Tab load notice: {e}", level="warn")

        self.is_open = True

    async def get_page(self, platform: str) -> Optional[Page]:
        page = self.pages.get(platform)
        if page and not page.is_closed():
            return page
        if self.context:
            page = await self.context.new_page()
            self.pages[platform] = page
            return page
        return None

    async def stop(self) -> None:
        self.is_open = False
        try:
            if self.context:
                await self.context.close()
        except Exception:
            pass
        try:
            if self._pw:
                await self._pw.stop()
        except Exception:
            pass
        self.context = None
        self._pw = None
        self.pages.clear()
        db.log_event("system", "Automation browser closed.")
