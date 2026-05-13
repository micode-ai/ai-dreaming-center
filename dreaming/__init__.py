"""ai-dreaming-center package init.

Sets the default asyncio policy to ProactorEventLoop on Windows. This
mostly affects loops we create ourselves (background threads, scheduler);
uvicorn's loop is created from its own `loop_factory` before we get a
chance to import, so we can't fix the asyncio.create_subprocess_exec
incompatibility that way — see dreaming.services._subprocess_compat for
how we actually launch child processes."""
import sys

if sys.platform == "win32":
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
