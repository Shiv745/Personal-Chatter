"""Anti-Ban Human-like Timing, Typing Simulation, and Rate Limiting."""
import asyncio
import random
import time
from collections import deque
from typing import Callable, Deque, Dict, List, Optional


class HourlyRateLimiter:
    """Tracks sent replies per platform over a rolling 60-minute window."""

    def __init__(self) -> None:
        self._timestamps: Dict[str, Deque[float]] = {
            "instagram": deque(),
            "whatsapp": deque(),
            "linkedin": deque(),
        }

    def _prune(self, platform: str) -> None:
        now = time.time()
        q = self._timestamps.setdefault(platform, deque())
        while q and (now - q[0]) > 3600:
            q.popleft()

    def count_last_hour(self, platform: str) -> int:
        self._prune(platform)
        return len(self._timestamps[platform])

    def can_send(self, platform: str, max_per_hour: int) -> bool:
        return self.count_last_hour(platform) < max_per_hour

    def record_send(self, platform: str) -> None:
        self._prune(platform)
        self._timestamps[platform].append(time.time())


async def human_read_delay(
    incoming_text: str,
    min_sec: float,
    max_sec: float,
    status_cb: Optional[Callable[[str], None]] = None,
) -> float:
    """Wait a realistic human reading + thinking duration proportional to message length."""
    extra = min(len(incoming_text) * 0.04, 4.0)
    delay = random.uniform(min_sec, max_sec) + random.uniform(0, extra)
    if status_cb:
        status_cb(f"Reading & thinking ({delay:.1f}s natural pause)...")
    await asyncio.sleep(delay)
    return delay


async def human_type_text(
    page,
    text: str,
    min_ms: int = 70,
    max_ms: int = 180,
    simulate_typo: bool = True,
    status_cb: Optional[Callable[[str], None]] = None,
) -> None:
    """Type character-by-character with variable speed, micro-pauses, and rare self-corrected typos."""
    avg_ms = (min_ms + max_ms) // 2
    if status_cb:
        status_cb(f"Typing naturally (~{avg_ms}ms/char)...")

    typo_done = False
    nearby_keys = {
        "a": "s", "s": "a", "e": "r", "r": "t", "i": "o", "o": "p", "n": "m", "t": "y"
    }

    for idx, ch in enumerate(text):
        # Occasional realistic typo + backspace (only ~18% chance per message, once max)
        if (
            simulate_typo
            and not typo_done
            and len(text) > 16
            and 4 < idx < len(text) - 4
            and ch.lower() in nearby_keys
            and random.random() < 0.025
        ):
            wrong = nearby_keys[ch.lower()]
            await page.keyboard.type(wrong, delay=random.randint(min_ms, max_ms))
            await asyncio.sleep(random.uniform(0.18, 0.42))
            await page.keyboard.press("Backspace")
            await asyncio.sleep(random.uniform(0.1, 0.25))
            typo_done = True

        # Typing speed varies naturally around spaces and punctuation
        char_delay = random.randint(min_ms, max_ms)
        if ch in ".,!?":
            char_delay += random.randint(80, 220)
        elif ch == " " and random.random() < 0.25:
            char_delay += random.randint(60, 180)

        await page.keyboard.type(ch, delay=char_delay)

        # Occasional brief mid-sentence thinking pause
        if ch == " " and random.random() < 0.06:
            await asyncio.sleep(random.uniform(0.35, 0.95))


async def send_multi_bubbles(
    page,
    input_locator,
    bubbles: List[str],
    type_min_ms: int,
    type_max_ms: int,
    send_key: str = "Enter",
    status_cb: Optional[Callable[[str], None]] = None,
) -> None:
    """Click input box and send 1..N short chat bubbles with natural pauses between them."""
    for i, bubble in enumerate(bubbles):
        clean = bubble.strip()
        if not clean:
            continue
        await input_locator.click()
        await asyncio.sleep(random.uniform(0.25, 0.6))
        await human_type_text(
            page,
            clean,
            min_ms=type_min_ms,
            max_ms=type_max_ms,
            simulate_typo=(i == 0),
            status_cb=status_cb,
        )
        await asyncio.sleep(random.uniform(0.2, 0.55))
        await page.keyboard.press(send_key)

        if i < len(bubbles) - 1:
            gap = random.uniform(1.1, 2.8)
            if status_cb:
                status_cb(f"Pausing {gap:.1f}s before next bubble...")
            await asyncio.sleep(gap)


def random_poll_sleep(min_sec: float, max_sec: float) -> float:
    return random.uniform(min_sec, max_sec)
