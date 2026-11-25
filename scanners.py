"""One-time slow human-like Profile & Song Scanners for Instagram and LinkedIn."""
import asyncio
import random
from pathlib import Path
from typing import Dict, List

import database as db
from brain import ChatBrain

SCREENSHOT_DIR = Path("screenshots")
SCREENSHOT_DIR.mkdir(exist_ok=True)


async def scan_instagram_profile(page, brain: ChatBrain, contact_id: int, handle: str) -> Dict[str, str]:
    """Opens Instagram profile once, slowly scrolls, inspects bio/captions/audio tags + screenshot."""
    clean_handle = handle.lstrip("@").strip()
    url = f"https://www.instagram.com/{clean_handle}/"
    db.log_event("instagram", f"Scanning Instagram profile @{clean_handle}...")

    await page.goto(url, wait_until="domcontentloaded", timeout=35000)
    await asyncio.sleep(random.uniform(3.0, 5.5))

    # Extract main header/bio/highlights text
    raw_chunks: List[str] = []
    audio_tags: List[str] = []

    try:
        header_text = await page.locator("header").inner_text(timeout=5000)
        raw_chunks.append("HEADER / BIO:\n" + header_text)
    except Exception:
        pass

    # Capture clean profile grid screenshot for Gemini Vision
    shot_path = SCREENSHOT_DIR / f"insta_{clean_handle}.png"
    try:
        await page.screenshot(path=str(shot_path), full_page=False)
    except Exception:
        shot_path = None

    # Slow human-like scroll to load recent posts
    for _ in range(2):
        await page.mouse.wheel(0, random.randint(450, 750))
        await asyncio.sleep(random.uniform(1.8, 3.2))

    # Collect image alt texts (Instagram puts rich descriptions & captions in alt text)
    try:
        imgs = page.locator("main img[alt]")
        count = min(await imgs.count(), 12)
        alts = []
        for i in range(count):
            alt = await imgs.nth(i).get_attribute("alt")
            if alt and len(alt) > 15:
                alts.append(alt)
        if alts:
            raw_chunks.append("RECENT POSTS ALT TEXT:\n" + "\n".join(alts))
    except Exception:
        pass

    # Gently check up to 3 recent posts/reels for captions & music/audio tracks
    try:
        post_links = page.locator("main a[href*='/p/'], main a[href*='/reel/']")
        total_links = min(await post_links.count(), 3)
        for i in range(total_links):
            await post_links.nth(i).click()
            await asyncio.sleep(random.uniform(2.5, 4.2))
            try:
                dialog_text = await page.locator("div[role='dialog']").inner_text(timeout=4000)
                raw_chunks.append(f"POST #{i+1}:\n{dialog_text[:700]}")
                # Look for audio link inside reel/post modal
                audio_links = page.locator("div[role='dialog'] a[href*='/reels/audio/']")
                if await audio_links.count() > 0:
                    audio_name = (await audio_links.first.inner_text()).strip()
                    if audio_name:
                        audio_tags.append(audio_name)
            except Exception:
                pass
            await page.keyboard.press("Escape")
            await asyncio.sleep(random.uniform(1.5, 2.8))
    except Exception:
        pass

    # Also check reels tab briefly if available for audio/captions
    raw_combined = "\n\n".join(raw_chunks) or f"Instagram user @{clean_handle}"
    intel = brain.analyze_instagram_profile(raw_combined, audio_tags, screenshot_path=shot_path)

    db.save_profile_intel(
        contact_id=contact_id,
        bio_summary=intel.get("bio_summary", ""),
        fav_songs=intel.get("fav_songs", ""),
        hobbies=intel.get("hobbies", ""),
        likes=intel.get("likes", ""),
        dislikes=intel.get("dislikes", ""),
        vibe_notes=intel.get("vibe_notes", ""),
    )
    db.log_event("instagram", f"Profile intel saved for @{clean_handle} (Songs: {intel.get('fav_songs', 'N/A')})")
    return intel


async def scan_linkedin_profile(page, brain: ChatBrain, contact_id: int, profile_url_or_handle: str) -> Dict[str, str]:
    """Slowly visits a LinkedIn profile once and saves Role, Company, Skills, Recent Activity."""
    target = profile_url_or_handle.strip()
    if target.startswith("http"):
        url = target
    else:
        url = f"https://www.linkedin.com/in/{target.strip('/')}/"

    db.log_event("linkedin", f"Scanning LinkedIn profile: {url}")
    await page.goto(url, wait_until="domcontentloaded", timeout=35000)
    await asyncio.sleep(random.uniform(3.5, 6.0))

    # Check for login/checkpoint
    if "checkpoint" in page.url or "authwall" in page.url:
        db.log_event("linkedin", "LinkedIn security check detected during scan. Paused.", level="warn")
        return {}

    # Slow human-like scroll through About, Experience, Skills, Activity
    for _ in range(4):
        await page.mouse.wheel(0, random.randint(500, 850))
        await asyncio.sleep(random.uniform(1.6, 3.0))

    try:
        main_text = await page.locator("main").inner_text(timeout=6000)
    except Exception:
        main_text = await page.inner_text("body")

    intel = brain.analyze_linkedin_profile(main_text)
    db.save_profile_intel(
        contact_id=contact_id,
        role_company=intel.get("role_company", ""),
        bio_summary=intel.get("bio_summary", ""),
        skills=intel.get("skills", ""),
        recent_activity=intel.get("recent_activity", ""),
        conversation_goal=intel.get("conversation_goal", ""),
    )
    db.log_event("linkedin", f"LinkedIn intel saved: {intel.get('role_company', target)}")
    return intel
