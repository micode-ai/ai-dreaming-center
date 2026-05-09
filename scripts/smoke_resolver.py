"""Smoke check: verify app.state.resolver_factory is bound after lifespan startup."""
import asyncio
from dreaming.main import app


async def go():
    async with app.router.lifespan_context(app):
        rf = getattr(app.state, "resolver_factory", None)
        print("resolver_factory =", rf)
        assert rf is not None, "resolver_factory NOT bound on app.state"
        print("OK")


if __name__ == "__main__":
    asyncio.run(go())
