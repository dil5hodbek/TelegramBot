import asyncio
import logging
import time
from io import BytesIO
from typing import Any, Dict, List, Tuple

from aiogram import Bot
from aiogram.methods.base import TelegramMethod
from aiogram.types import Message, User

from .models import ProfileSnapshot

logger = logging.getLogger(__name__)


class GetUserPersonalChatMessages(TelegramMethod[List[Message]]):
    """Telegram Bot API'dagi profil kanalining oxirgi postlarini olish metodi."""

    __returning__ = List[Message]
    __api_method__ = "getUserPersonalChatMessages"

    user_id: int
    limit: int

    def __init__(self, *, user_id: int, limit: int = 3, **kwargs: Any) -> None:
        super().__init__(user_id=user_id, limit=max(1, min(limit, 20)), **kwargs)


class ProfileLoader:
    def __init__(self, ttl_seconds: int = 3600, max_photos: int = 5) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_photos = max(1, min(max_photos, 10))
        self._cache: Dict[int, Tuple[float, ProfileSnapshot]] = {}
        self._inflight: Dict[int, asyncio.Task[ProfileSnapshot]] = {}

    async def load(self, bot: Bot, user: User) -> ProfileSnapshot:
        cached = self._cache.get(user.id)
        now = time.monotonic()
        if cached and cached[0] > now:
            return cached[1]

        # Bir profil ketma-ket bir necha xabar yozsa, bir xil Telegram so'rovlari
        # qayta yuborilmaydi; barcha xabarlar bitta davom etayotgan tekshiruvni kutadi.
        existing = self._inflight.get(user.id)
        if existing:
            return await existing
        task = asyncio.create_task(self._load_uncached(bot, user))
        self._inflight[user.id] = task
        try:
            snapshot = await task
            self._cache[user.id] = (time.monotonic() + self.ttl_seconds, snapshot)
            return snapshot
        finally:
            if self._inflight.get(user.id) is task:
                self._inflight.pop(user.id, None)

    async def _load_uncached(self, bot: Bot, user: User) -> ProfileSnapshot:
        async def load_chat_details() -> Tuple[str, Any, str, str, str]:
            bio = ""
            personal_channel_id = None
            personal_channel_title = ""
            personal_channel_username = ""
            personal_channel_description = ""
            try:
                chat = await bot.get_chat(user.id)
                bio = getattr(chat, "bio", None) or ""
                personal_chat = getattr(chat, "personal_chat", None)
                if personal_chat:
                    personal_channel_id = personal_chat.id
                    personal_channel_title = getattr(personal_chat, "title", None) or ""
                    personal_channel_username = (
                        getattr(personal_chat, "username", None) or ""
                    )
                    try:
                        channel = await bot.get_chat(personal_chat.id)
                        personal_channel_title = (
                            getattr(channel, "title", None) or personal_channel_title
                        )
                        personal_channel_username = (
                            getattr(channel, "username", None)
                            or personal_channel_username
                        )
                        personal_channel_description = (
                            getattr(channel, "description", None) or ""
                        )
                    except Exception as exc:
                        logger.debug(
                            "Profil kanali tafsiloti olinmadi user_id=%s channel_id=%s: %s",
                            user.id,
                            personal_chat.id,
                            exc,
                        )
            except Exception as exc:
                # Telegram barcha userlar uchun bio'ni bermasligi mumkin.
                logger.debug("Bio olinmadi user_id=%s: %s", user.id, exc)
            return (
                bio,
                personal_channel_id,
                personal_channel_title,
                personal_channel_username,
                personal_channel_description,
            )

        async def load_recent_posts() -> Tuple[str, Any, str, str]:
            personal_channel_id = None
            personal_channel_title = ""
            personal_channel_username = ""
            recent_parts = []
            try:
                recent_messages = await bot(
                    GetUserPersonalChatMessages(user_id=user.id, limit=3)
                )
                for item in recent_messages:
                    item_text = (item.text or item.caption or "").strip()
                    if item_text:
                        recent_parts.append(item_text[:1000])
                    if personal_channel_id is None:
                        personal_channel_id = item.chat.id
                        personal_channel_title = item.chat.title or ""
                        personal_channel_username = item.chat.username or ""
            except Exception as exc:
                # Eski Bot API versiyasi yoki shaxsiy kanali yo'q profil bo'lishi mumkin.
                logger.debug("Profil kanal postlari olinmadi user_id=%s: %s", user.id, exc)
            return (
                "\n".join(recent_parts)[:3000],
                personal_channel_id,
                personal_channel_title,
                personal_channel_username,
            )

        async def load_photos() -> Tuple[bytes, ...]:
            try:
                photos = await bot.get_user_profile_photos(
                    user.id, limit=self.max_photos
                )
            except Exception as exc:
                logger.warning("Profil rasmi olinmadi user_id=%s: %s", user.id, exc)
                return ()

            async def download_photo(sizes: Any) -> bytes:
                if not sizes:
                    return b""
                try:
                    buffer = BytesIO()
                    await bot.download(sizes[-1].file_id, destination=buffer)
                    return buffer.getvalue()
                except Exception as exc:
                    logger.debug(
                        "Profil rasmi yuklanmadi user_id=%s: %s", user.id, exc
                    )
                    return b""

            downloaded = await asyncio.gather(
                *(download_photo(sizes) for sizes in photos.photos[: self.max_photos])
            )
            return tuple(value for value in downloaded if value)

        chat_details, recent_details, photo_samples = await asyncio.gather(
            load_chat_details(),
            load_recent_posts(),
            load_photos(),
        )
        (
            bio,
            personal_channel_id,
            personal_channel_title,
            personal_channel_username,
            personal_channel_description,
        ) = chat_details
        (
            personal_channel_recent_text,
            recent_channel_id,
            recent_channel_title,
            recent_channel_username,
        ) = recent_details
        if personal_channel_id is None and recent_channel_id is not None:
            personal_channel_id = recent_channel_id
            personal_channel_title = recent_channel_title
            personal_channel_username = recent_channel_username

        snapshot = ProfileSnapshot(
            user_id=user.id,
            full_name=user.full_name,
            username=user.username or "",
            bio=bio,
            personal_channel_id=personal_channel_id,
            personal_channel_title=personal_channel_title,
            personal_channel_username=personal_channel_username,
            personal_channel_description=personal_channel_description,
            personal_channel_recent_text=personal_channel_recent_text,
            photo_bytes=photo_samples[0] if photo_samples else None,
            photo_samples=photo_samples,
        )
        return snapshot
