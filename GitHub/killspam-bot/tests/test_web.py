"""Run: python -m pytest tests/test_web.py  (or full suite). No network needed.

Covers spam_bot/web.py via aiohttp TestClient: form rendering, key storage,
single-use enforcement, and the health endpoint.
"""
import asyncio
import os
import tempfile

_db_fd, _db_path = tempfile.mkstemp(suffix=".db")
os.close(_db_fd)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_db_path}")

from cryptography.fernet import Fernet
os.environ["KEY_ENCRYPTION_SECRET"] = Fernet.generate_key().decode()

# Create tables before any code under test runs.
from spam_bot.db.session import engine, Base
from spam_bot.db.models import TokenGrant, GroupConfig  # register tables  # noqa: F401
Base.metadata.create_all(bind=engine)

from spam_bot.core import tokens, keys
from spam_bot import web as spam_web
from aiohttp.test_utils import TestClient, TestServer

# Monkeypatch validate_gemini_key globally so no live API call is made.
spam_web.validate_gemini_key = lambda key: True


def _build_client():
    """Fresh TestClient wrapping a fresh app instance."""
    return TestClient(TestServer(spam_web.build_app()))


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------

def test_health_returns_ok():
    async def _run():
        async with _build_client() as client:
            resp = await client.get("/health")
            assert resp.status == 200
            data = await resp.json()
            assert data["status"] == "ok"
    asyncio.run(_run())


# ---------------------------------------------------------------------------
# GET /key
# ---------------------------------------------------------------------------

def test_get_key_valid_token_shows_form():
    async def _run():
        tok = tokens.mint(chat_id=3001, created_by=777)
        assert tok is not None
        async with _build_client() as client:
            resp = await client.get(f"/key?t={tok}")
            assert resp.status == 200
            text = await resp.text()
            assert "<form" in text
            assert "paste" in text.lower() or "gemini" in text.lower()
    asyncio.run(_run())


def test_get_key_bad_token_shows_expired():
    async def _run():
        async with _build_client() as client:
            resp = await client.get("/key?t=nosuchtoken")
            assert resp.status == 200
            text = await resp.text()
            assert "expired" in text.lower() or "invalid" in text.lower()
    asyncio.run(_run())


def test_get_key_no_token_shows_expired():
    async def _run():
        async with _build_client() as client:
            resp = await client.get("/key")
            assert resp.status == 200
            text = await resp.text()
            assert "expired" in text.lower() or "invalid" in text.lower()
    asyncio.run(_run())


# ---------------------------------------------------------------------------
# POST /key
# ---------------------------------------------------------------------------

def test_post_key_stores_and_shows_success():
    async def _run():
        tok = tokens.mint(chat_id=3002, created_by=777)
        async with _build_client() as client:
            resp = await client.post("/key", data={"t": tok, "key": "AIzaSyFakeKey1"})
            assert resp.status == 200
            text = await resp.text()
            assert "moderation is on" in text.lower() or "ai moderation" in text.lower()
        # Key must be retrievable from the DB after the POST.
        assert keys.get_key(3002) == "AIzaSyFakeKey1"
    asyncio.run(_run())


def test_post_key_single_use():
    """Second POST with the same token is rejected (token consumed after first success)."""
    async def _run():
        tok = tokens.mint(chat_id=3003, created_by=777)
        async with _build_client() as client:
            resp1 = await client.post("/key", data={"t": tok, "key": "AIzaSyFirst"})
            assert resp1.status == 200
            text1 = await resp1.text()
            assert "moderation is on" in text1.lower() or "ai moderation" in text1.lower()

            resp2 = await client.post("/key", data={"t": tok, "key": "AIzaSySecond"})
            assert resp2.status == 200
            text2 = await resp2.text()
            assert "expired" in text2.lower() or "invalid" in text2.lower()
        # Key remains the FIRST value (second POST was rejected).
        assert keys.get_key(3003) == "AIzaSyFirst"
    asyncio.run(_run())


def test_post_key_missing_key_field():
    async def _run():
        tok = tokens.mint(chat_id=3004, created_by=777)
        async with _build_client() as client:
            resp = await client.post("/key", data={"t": tok, "key": ""})
            assert resp.status == 200
            text = await resp.text()
            assert "no key" in text.lower() or "missing" in text.lower()
    asyncio.run(_run())


def test_post_key_bad_token():
    async def _run():
        async with _build_client() as client:
            resp = await client.post("/key", data={"t": "badtoken", "key": "AIzaSyAny"})
            assert resp.status == 200
            text = await resp.text()
            assert "expired" in text.lower() or "invalid" in text.lower()
    asyncio.run(_run())
