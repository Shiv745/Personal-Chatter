"""PulseAI Agent — Windows Desktop Application Entry Point."""
import asyncio
import sys
import threading
import time
import webbrowser
from aiohttp import web

import config_manager
from engine import AgentEngine
from server import create_app


def start_backend_thread(engine: AgentEngine, port: int, ready_event: threading.Event) -> None:
    """Runs the asyncio aiohttp server + Playwright automation loop in a dedicated thread."""
    async def runner():
        app = create_app(engine)
        site_runner = web.AppRunner(app)
        await site_runner.setup()
        site = web.TCPSite(site_runner, "127.0.0.1", port)
        await site.start()
        ready_event.set()
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            await engine.stop_engine()
            await site_runner.cleanup()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(runner())
    except KeyboardInterrupt:
        pass


def main() -> None:
    cfg = config_manager.load_config()
    port = int(cfg.get("server_port", 8765))
    url = f"http://127.0.0.1:{port}"

    engine = AgentEngine()
    ready = threading.Event()

    t = threading.Thread(target=start_backend_thread, args=(engine, port, ready), daemon=True)
    t.start()
    ready.wait(timeout=10)

    force_web = "--web" in sys.argv

    if not force_web:
        try:
            import webview

            window = webview.create_window(
                title="PulseAI Agent — Windows Desktop",
                url=url,
                width=1380,
                height=860,
                min_size=(1100, 700),
                background_color="#0d1117",
            )
            webview.start(debug=False)
            return
        except Exception as e:
            print(f"[Notice] PyWebView native window unavailable ({e}). Opening in browser instead...")

    print(f"PulseAI Dashboard running at {url}")
    webbrowser.open(url)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down PulseAI Agent...")


if __name__ == "__main__":
    main()
