import os
from dataclasses import dataclass
from pathlib import Path
from typing import FrozenSet, Optional

from dotenv import load_dotenv


def _as_bool(value: str, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _optional_int(value: str) -> Optional[int]:
    if not value or not value.strip():
        return None
    return int(value.strip())


def _admin_ids(value: str) -> FrozenSet[int]:
    if not value:
        return frozenset()
    return frozenset(int(item.strip()) for item in value.split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    bot_token: str
    openai_api_key: Optional[str]
    openai_moderation_enabled: bool
    dry_run: bool
    review_threshold: int
    delete_threshold: int
    ban_threshold: int
    mod_log_chat_id: Optional[int]
    admin_ids: FrozenSet[int]
    protected_chat_id: Optional[int]
    database_path: Path
    profile_cache_ttl_seconds: int
    profile_photo_limit: int
    duplicate_window_seconds: int
    coordinated_window_seconds: int
    coordinated_min_users: int
    data_retention_days: int
    ai_user_limit: int
    ai_user_window_seconds: int
    ai_global_limit: int
    ai_global_window_seconds: int
    limited_admin_id: int = 785292062
    limited_admin_chat_id: int = -1001223866194

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        token = os.getenv("BOT_TOKEN", "").strip()
        if not token or token == "replace_with_new_botfather_token":
            raise RuntimeError("BOT_TOKEN topilmadi. .env fayliga yangi BotFather tokenini yozing.")

        review = int(os.getenv("REVIEW_THRESHOLD", "35"))
        delete = int(os.getenv("DELETE_THRESHOLD", "60"))
        ban = int(os.getenv("BAN_THRESHOLD", "85"))
        if not 0 <= review < delete < ban:
            raise RuntimeError(
                "Chegaralar REVIEW_THRESHOLD < DELETE_THRESHOLD < BAN_THRESHOLD bo'lishi kerak."
            )

        profile_photo_limit = max(1, min(int(os.getenv("PROFILE_PHOTO_LIMIT", "5")), 10))
        coordinated_min_users = max(3, int(os.getenv("COORDINATED_MIN_USERS", "3")))

        openai_key = os.getenv("OPENAI_API_KEY", "").strip() or None
        return cls(
            bot_token=token,
            openai_api_key=openai_key,
            openai_moderation_enabled=_as_bool(
                os.getenv("OPENAI_MODERATION_ENABLED"), default=True
            ),
            dry_run=_as_bool(os.getenv("DRY_RUN"), default=True),
            review_threshold=review,
            delete_threshold=delete,
            ban_threshold=ban,
            mod_log_chat_id=_optional_int(os.getenv("MOD_LOG_CHAT_ID", "")),
            admin_ids=_admin_ids(os.getenv("ADMIN_IDS", "")),
            protected_chat_id=_optional_int(os.getenv("PROTECTED_CHAT_ID", "")),
            database_path=Path(os.getenv("DATABASE_PATH", "data/izoh_posbon.db")),
            profile_cache_ttl_seconds=int(os.getenv("PROFILE_CACHE_TTL_SECONDS", "3600")),
            profile_photo_limit=profile_photo_limit,
            duplicate_window_seconds=int(os.getenv("DUPLICATE_WINDOW_SECONDS", "86400")),
            coordinated_window_seconds=max(
                30, int(os.getenv("COORDINATED_WINDOW_SECONDS", "120"))
            ),
            coordinated_min_users=coordinated_min_users,
            data_retention_days=max(7, int(os.getenv("DATA_RETENTION_DAYS", "90"))),
            ai_user_limit=max(1, int(os.getenv("AI_USER_LIMIT", "10"))),
            ai_user_window_seconds=max(
                5, int(os.getenv("AI_USER_WINDOW_SECONDS", "30"))
            ),
            ai_global_limit=max(10, int(os.getenv("AI_GLOBAL_LIMIT", "120"))),
            ai_global_window_seconds=max(
                10, int(os.getenv("AI_GLOBAL_WINDOW_SECONDS", "60"))
            ),
        )
