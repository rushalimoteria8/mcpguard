from __future__ import annotations

import asyncio
from pathlib import Path

from aiohttp import web


DEMO_ROOT = Path(__file__).resolve().parent / "demo_workspace"
DEMO_ROOT.mkdir(parents=True, exist_ok=True)


async def read_file(request: web.Request) -> web.Response:
    payload = await request.json()
    parameters = payload.get("parameters", {})
    file_path = parameters.get("file_path", "notes.txt")

    target_file = DEMO_ROOT / file_path
    if target_file.exists():
        content = target_file.read_text(encoding="utf-8")
    else:
        content = f"Demo content for {file_path}"

    # Include secret-like values so MCPGuard can visibly redact them in the demo.
    return web.json_response(
        {
            "content": content,
            "token": "ghp_abcdefghijklmnopqrstuvwxyz123456",
            "authorization": "Bearer abcdefghijklmnopqrstuvwxyz0123456789",
        }
    )


async def write_file(request: web.Request) -> web.Response:
    payload = await request.json()
    parameters = payload.get("parameters", {})
    file_path = parameters.get("file_path", "notes.txt")
    content = parameters.get("content", "")

    target_file = DEMO_ROOT / file_path
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text(str(content), encoding="utf-8")

    return web.json_response(
        {
            "status": "written",
            "file_path": file_path,
            "bytes_written": len(str(content).encode("utf-8")),
        }
    )


async def health(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


def create_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/health", health)
    app.router.add_post("/read", read_file)
    app.router.add_post("/write", write_file)
    return app


async def main() -> None:
    app = create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 3001)
    await site.start()
    print("Demo backend running on http://127.0.0.1:3001")

    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
