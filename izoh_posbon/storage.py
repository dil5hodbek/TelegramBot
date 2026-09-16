import hashlib
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import aiosqlite

from .models import ModerationDecision


def message_fingerprint(text: str) -> str:
    normalized = " ".join(text.casefold().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class Storage:
    def __init__(
        self,
        path: Path,
        duplicate_window_seconds: int,
        data_retention_days: int = 90,
    ) -> None:
        self.path = path
        self.duplicate_window_seconds = duplicate_window_seconds
        self.data_retention_days = max(7, data_retention_days)

    async def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.path) as db:
            await db.executescript(
                """
                CREATE TABLE IF NOT EXISTS message_fingerprints (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    fingerprint TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_fingerprint_lookup
                ON message_fingerprints(user_id, fingerprint, created_at);

                CREATE TABLE IF NOT EXISTS moderation_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    score INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    reasons_json TEXT NOT NULL,
                    message_text TEXT NOT NULL,
                    full_name TEXT NOT NULL DEFAULT '',
                    username TEXT NOT NULL DEFAULT '',
                    chat_title TEXT NOT NULL DEFAULT '',
                    created_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_events_user
                ON moderation_events(chat_id, user_id, created_at);

                CREATE TABLE IF NOT EXISTS pending_actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    chat_title TEXT NOT NULL DEFAULT '',
                    user_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    full_name TEXT NOT NULL DEFAULT '',
                    username TEXT NOT NULL DEFAULT '',
                    message_text TEXT NOT NULL DEFAULT '',
                    score INTEGER NOT NULL,
                    reasons_json TEXT NOT NULL DEFAULT '[]',
                    is_test INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'pending',
                    result TEXT NOT NULL DEFAULT '',
                    created_at INTEGER NOT NULL,
                    decided_at INTEGER,
                    decided_by INTEGER
                );
                CREATE INDEX IF NOT EXISTS idx_pending_status
                ON pending_actions(status, created_at);

                CREATE TABLE IF NOT EXISTS managed_chats (
                    chat_id INTEGER PRIMARY KEY,
                    title TEXT NOT NULL DEFAULT '',
                    username TEXT NOT NULL DEFAULT '',
                    active INTEGER NOT NULL DEFAULT 1,
                    added_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS admin_preferences (
                    admin_id INTEGER PRIMARY KEY,
                    selected_chat_id INTEGER,
                    updated_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS bot_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS blocked_users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    full_name TEXT NOT NULL DEFAULT '',
                    username TEXT NOT NULL DEFAULT '',
                    reason TEXT NOT NULL DEFAULT '',
                    action TEXT NOT NULL DEFAULT 'ban',
                    is_permanent INTEGER NOT NULL DEFAULT 1,
                    blocked_at INTEGER NOT NULL,
                    unblocked_at INTEGER,
                    unblocked_by INTEGER
                );
                CREATE INDEX IF NOT EXISTS idx_blocked_lookup
                ON blocked_users(chat_id, user_id, blocked_at DESC);

                CREATE TABLE IF NOT EXISTS profile_checks (
                    chat_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    full_name TEXT NOT NULL DEFAULT '',
                    username TEXT NOT NULL DEFAULT '',
                    bio_hash TEXT NOT NULL DEFAULT '',
                    photo_count INTEGER NOT NULL DEFAULT 0,
                    check_count INTEGER NOT NULL DEFAULT 1,
                    max_score INTEGER NOT NULL DEFAULT 0,
                    last_action TEXT NOT NULL DEFAULT 'allow',
                    reasons_json TEXT NOT NULL DEFAULT '[]',
                    first_checked_at INTEGER NOT NULL,
                    last_checked_at INTEGER NOT NULL,
                    PRIMARY KEY(chat_id, user_id)
                );
                CREATE INDEX IF NOT EXISTS idx_profile_checks_time
                ON profile_checks(last_checked_at);

                CREATE TABLE IF NOT EXISTS learned_patterns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER,
                    pattern TEXT NOT NULL,
                    normalized_pattern TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT 'spam',
                    added_by INTEGER NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_learned_patterns_chat
                ON learned_patterns(chat_id, enabled, created_at);

                CREATE TABLE IF NOT EXISTS ai_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER,
                    user_id INTEGER,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    category_scores_json TEXT NOT NULL DEFAULT '{}',
                    created_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_ai_usage_chat_time
                ON ai_usage(chat_id, created_at);

                CREATE TABLE IF NOT EXISTS emoji_violations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    violation_count INTEGER NOT NULL DEFAULT 1,
                    created_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_emoji_violations_lookup
                ON emoji_violations(chat_id, user_id, created_at);

                CREATE TABLE IF NOT EXISTS link_violations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    violation_count INTEGER NOT NULL DEFAULT 1,
                    created_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_link_violations_lookup
                ON link_violations(chat_id, user_id, created_at);

                CREATE TABLE IF NOT EXISTS bot_messages (
                    chat_id INTEGER NOT NULL,
                    bot_user_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    created_at INTEGER NOT NULL,
                    PRIMARY KEY(chat_id, message_id)
                );
                CREATE INDEX IF NOT EXISTS idx_bot_messages_lookup
                ON bot_messages(chat_id, bot_user_id, message_id DESC);
                """
            )
            columns = {
                row[1]
                for row in await (
                    await db.execute("PRAGMA table_info(moderation_events)")
                ).fetchall()
            }
            migrations = {
                "full_name": "TEXT NOT NULL DEFAULT ''",
                "username": "TEXT NOT NULL DEFAULT ''",
                "chat_title": "TEXT NOT NULL DEFAULT ''",
                "ai_categories_json": "TEXT NOT NULL DEFAULT '{}'",
            }
            for column, definition in migrations.items():
                if column not in columns:
                    await db.execute(
                        "ALTER TABLE moderation_events ADD COLUMN "
                        + column
                        + " "
                        + definition
                    )
            retention_cutoff = int(time.time()) - (self.data_retention_days * 86400)
            await db.execute(
                "DELETE FROM message_fingerprints WHERE created_at < ?",
                (retention_cutoff,),
            )
            await db.execute(
                "DELETE FROM profile_checks WHERE last_checked_at < ?",
                (retention_cutoff,),
            )
            await db.execute(
                "DELETE FROM ai_usage WHERE created_at < ?",
                (retention_cutoff,),
            )
            await db.execute(
                "DELETE FROM pending_actions WHERE status != 'pending' AND created_at < ?",
                (retention_cutoff,),
            )
            await db.execute(
                "DELETE FROM bot_messages WHERE created_at < ?",
                (retention_cutoff,),
            )
            await db.commit()

    async def get_state(self, key: str) -> Optional[str]:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                "SELECT value FROM bot_state WHERE key = ?",
                (key,),
            )
            row = await cursor.fetchone()
        return str(row[0]) if row else None

    async def set_state(self, key: str, value: str) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT INTO bot_state(key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (key, value, int(time.time())),
            )
            await db.commit()

    async def duplicate_count(
        self, user_id: int, text: str, chat_id: Optional[int] = None
    ) -> int:
        if not text.strip():
            return 0
        fingerprint = message_fingerprint(text)
        cutoff = int(time.time()) - self.duplicate_window_seconds
        async with aiosqlite.connect(self.path) as db:
            if chat_id is None:
                cursor = await db.execute(
                    """
                    SELECT COUNT(*) FROM message_fingerprints
                    WHERE user_id = ? AND fingerprint = ? AND created_at >= ?
                    """,
                    (user_id, fingerprint, cutoff),
                )
            else:
                cursor = await db.execute(
                    """
                    SELECT COUNT(*) FROM message_fingerprints
                    WHERE chat_id = ? AND user_id = ?
                      AND fingerprint = ? AND created_at >= ?
                    """,
                    (chat_id, user_id, fingerprint, cutoff),
                )
            row = await cursor.fetchone()
        return int(row[0]) if row else 0

    async def coordinated_user_count(
        self,
        chat_id: int,
        user_id: int,
        text: str,
        window_seconds: int = 120,
    ) -> int:
        normalized = " ".join(text.casefold().split())
        if len(normalized) < 12:
            return 0
        fingerprint = message_fingerprint(text)
        cutoff = int(time.time()) - max(30, window_seconds)
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """
                SELECT user_id FROM message_fingerprints
                WHERE chat_id = ? AND fingerprint = ? AND created_at >= ?
                GROUP BY user_id
                """,
                (chat_id, fingerprint, cutoff),
            )
            users = {int(row[0]) for row in await cursor.fetchall()}
        users.add(user_id)
        return len(users)

    async def record_message(self, chat_id: int, user_id: int, text: str) -> None:
        if not text.strip():
            return
        now = int(time.time())
        fingerprint = message_fingerprint(text)
        cutoff = now - (self.duplicate_window_seconds * 2)
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT INTO message_fingerprints(chat_id, user_id, fingerprint, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (chat_id, user_id, fingerprint, now),
            )
            await db.execute(
                "DELETE FROM message_fingerprints WHERE created_at < ?", (cutoff,)
            )
            await db.commit()

    async def record_emoji_violation(
        self,
        chat_id: int,
        user_id: int,
    ) -> int:
        """Bitta qoidabuzar xabarni yozadi va shu userning jami urinishini qaytaradi."""
        now = int(time.time())
        async with aiosqlite.connect(self.path) as db:
            await db.execute("BEGIN IMMEDIATE")
            await db.execute(
                """
                INSERT INTO emoji_violations(
                    chat_id, user_id, violation_count, created_at
                ) VALUES (?, ?, ?, ?)
                """,
                (chat_id, user_id, 1, now),
            )
            cursor = await db.execute(
                """
                SELECT COALESCE(SUM(violation_count), 0)
                FROM emoji_violations
                WHERE chat_id = ? AND user_id = ?
                """,
                (chat_id, user_id),
            )
            row = await cursor.fetchone()
            await db.commit()
        return int(row[0] or 0) if row else 1

    async def clear_emoji_violations(self, chat_id: int, user_id: int) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "DELETE FROM emoji_violations WHERE chat_id = ? AND user_id = ?",
                (chat_id, user_id),
            )
            await db.commit()

    async def record_link_violation(self, chat_id: int, user_id: int) -> int:
        """Havolali xabarni yozadi va userning shu guruhdagi jami urinishini qaytaradi."""
        now = int(time.time())
        async with aiosqlite.connect(self.path) as db:
            await db.execute("BEGIN IMMEDIATE")
            await db.execute(
                """
                INSERT INTO link_violations(
                    chat_id, user_id, violation_count, created_at
                ) VALUES (?, ?, ?, ?)
                """,
                (chat_id, user_id, 1, now),
            )
            cursor = await db.execute(
                """
                SELECT COALESCE(SUM(violation_count), 0)
                FROM link_violations
                WHERE chat_id = ? AND user_id = ?
                """,
                (chat_id, user_id),
            )
            row = await cursor.fetchone()
            await db.commit()
        return int(row[0] or 0) if row else 1

    async def clear_link_violations(self, chat_id: int, user_id: int) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "DELETE FROM link_violations WHERE chat_id = ? AND user_id = ?",
                (chat_id, user_id),
            )
            await db.commit()

    async def record_bot_message(
        self,
        chat_id: int,
        bot_user_id: int,
        message_id: int,
    ) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT OR IGNORE INTO bot_messages(
                    chat_id, bot_user_id, message_id, created_at
                ) VALUES (?, ?, ?, ?)
                """,
                (chat_id, bot_user_id, message_id, int(time.time())),
            )
            await db.commit()

    async def recent_bot_message_ids(
        self,
        chat_id: int,
        bot_user_id: int,
        limit: int,
    ) -> List[int]:
        safe_limit = max(1, min(int(limit), 100))
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """
                SELECT message_id FROM bot_messages
                WHERE chat_id = ? AND bot_user_id = ?
                ORDER BY message_id DESC
                LIMIT ?
                """,
                (chat_id, bot_user_id, safe_limit),
            )
            rows = await cursor.fetchall()
        return [int(row[0]) for row in rows]

    async def tracked_bot_user_ids(self, chat_id: int) -> List[int]:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """
                SELECT bot_user_id, MAX(created_at) AS last_seen
                FROM bot_messages
                WHERE chat_id = ?
                GROUP BY bot_user_id
                ORDER BY last_seen DESC, bot_user_id
                """,
                (chat_id,),
            )
            rows = await cursor.fetchall()
        return [int(row[0]) for row in rows]

    async def remove_bot_message_records(
        self,
        chat_id: int,
        message_ids: Sequence[int],
    ) -> None:
        ids = tuple(int(item) for item in message_ids)
        if not ids:
            return
        placeholders = ",".join("?" for _ in ids)
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "DELETE FROM bot_messages WHERE chat_id = ? AND message_id IN ("
                + placeholders
                + ")",
                (chat_id, *ids),
            )
            await db.commit()

    async def record_event(
        self,
        chat_id: int,
        user_id: int,
        message_id: int,
        text: str,
        decision: ModerationDecision,
        full_name: str = "",
        username: str = "",
        chat_title: str = "",
    ) -> None:
        reasons: Sequence[dict] = [
            {"code": signal.code, "points": signal.points, "detail": signal.detail}
            for signal in decision.signals
        ]
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT INTO moderation_events(
                    chat_id, user_id, message_id, score, action,
                    reasons_json, message_text, full_name, username,
                    chat_title, ai_categories_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chat_id,
                    user_id,
                    message_id,
                    decision.score,
                    decision.action.value,
                    json.dumps(reasons, ensure_ascii=False),
                    text[:1000],
                    full_name[:255],
                    username[:64],
                    chat_title[:255],
                    json.dumps(decision.ai_categories, ensure_ascii=False),
                    int(time.time()),
                ),
            )
            await db.commit()

    async def record_profile_check(
        self,
        chat_id: int,
        user_id: int,
        full_name: str,
        username: str,
        bio: str,
        photo_count: int,
        decision: ModerationDecision,
    ) -> None:
        now = int(time.time())
        reasons = [
            {"code": item.code, "points": item.points, "detail": item.detail}
            for item in decision.signals
        ]
        bio_hash = hashlib.sha256((bio or "").encode("utf-8")).hexdigest()
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT INTO profile_checks(
                    chat_id, user_id, full_name, username, bio_hash, photo_count,
                    check_count, max_score, last_action, reasons_json,
                    first_checked_at, last_checked_at
                ) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?)
                ON CONFLICT(chat_id, user_id) DO UPDATE SET
                    full_name = excluded.full_name,
                    username = excluded.username,
                    bio_hash = excluded.bio_hash,
                    photo_count = excluded.photo_count,
                    check_count = profile_checks.check_count + 1,
                    max_score = MAX(profile_checks.max_score, excluded.max_score),
                    last_action = excluded.last_action,
                    reasons_json = excluded.reasons_json,
                    last_checked_at = excluded.last_checked_at
                """,
                (
                    chat_id,
                    user_id,
                    full_name[:255],
                    username[:64],
                    bio_hash,
                    max(0, photo_count),
                    decision.score,
                    decision.action.value,
                    json.dumps(reasons, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            await db.commit()

    async def record_ai_usage(
        self,
        chat_id: Optional[int],
        user_id: Optional[int],
        provider: str,
        model: str,
        category_scores: Dict[str, float],
    ) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT INTO ai_usage(
                    chat_id, user_id, provider, model,
                    category_scores_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    chat_id,
                    user_id,
                    provider[:40],
                    model[:100],
                    json.dumps(category_scores, ensure_ascii=False),
                    int(time.time()),
                ),
            )
            await db.commit()

    async def record_blocked_user(
        self,
        chat_id: int,
        user_id: int,
        full_name: str,
        username: str,
        reason: str,
        action: str = "ban",
        is_permanent: bool = True,
    ) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT INTO blocked_users(
                    chat_id, user_id, full_name, username, reason, action,
                    is_permanent, blocked_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chat_id,
                    user_id,
                    full_name[:255],
                    username[:64],
                    reason[:1000],
                    action[:30],
                    1 if is_permanent else 0,
                    int(time.time()),
                ),
            )
            await db.commit()

    async def mark_unblocked_user(
        self, chat_id: int, user_id: int, admin_id: int
    ) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                UPDATE blocked_users
                SET unblocked_at = ?, unblocked_by = ?
                WHERE id = (
                    SELECT id FROM blocked_users
                    WHERE chat_id = ? AND user_id = ? AND unblocked_at IS NULL
                    ORDER BY blocked_at DESC, id DESC LIMIT 1
                )
                """,
                (int(time.time()), admin_id, chat_id, user_id),
            )
            await db.commit()

    async def add_learned_pattern(
        self,
        chat_id: Optional[int],
        pattern: str,
        added_by: int,
        category: str = "spam",
    ) -> int:
        cleaned = " ".join(pattern.casefold().split())
        if len(cleaned) < 3:
            raise ValueError("Pattern juda qisqa")
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """
                INSERT INTO learned_patterns(
                    chat_id, pattern, normalized_pattern, category,
                    added_by, enabled, created_at
                ) VALUES (?, ?, ?, ?, ?, 1, ?)
                """,
                (
                    chat_id,
                    pattern[:255],
                    cleaned[:255],
                    category[:30],
                    added_by,
                    int(time.time()),
                ),
            )
            await db.commit()
            return int(cursor.lastrowid)

    async def learned_patterns(self, chat_id: int) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT * FROM learned_patterns
                WHERE enabled = 1 AND (chat_id IS NULL OR chat_id = ?)
                ORDER BY chat_id IS NULL DESC, created_at DESC, id DESC
                """,
                (chat_id,),
            )
            rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def disable_learned_pattern(self, pattern_id: int, chat_id: int) -> bool:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """
                UPDATE learned_patterns SET enabled = 0
                WHERE id = ? AND chat_id = ? AND enabled = 1
                """,
                (pattern_id, chat_id),
            )
            await db.commit()
            return cursor.rowcount == 1

    async def database_stats(self, chat_id: Optional[int] = None) -> Dict[str, int]:
        tables = (
            "moderation_events",
            "pending_actions",
            "blocked_users",
            "profile_checks",
            "learned_patterns",
            "ai_usage",
            "emoji_violations",
            "link_violations",
            "bot_messages",
            "managed_chats",
        )
        result: Dict[str, int] = {}
        async with aiosqlite.connect(self.path) as db:
            for table in tables:
                query = "SELECT COUNT(*) FROM " + table
                parameters: tuple = ()
                if chat_id is not None:
                    query += " WHERE chat_id = ?"
                    parameters = (chat_id,)
                cursor = await db.execute(query, parameters)
                row = await cursor.fetchone()
                result[table] = int(row[0] or 0) if row else 0
        return result

    async def user_stats(self, user_id: int) -> Dict[str, Any]:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM message_fingerprints WHERE user_id = ?",
                (user_id,),
            )
            messages_row = await cursor.fetchone()
            cursor = await db.execute(
                """
                SELECT
                    COUNT(*) AS flagged,
                    SUM(CASE WHEN action = 'review' THEN 1 ELSE 0 END) AS reviews,
                    SUM(CASE WHEN action = 'delete' THEN 1 ELSE 0 END) AS deletions,
                    SUM(CASE WHEN action = 'ban' THEN 1 ELSE 0 END) AS bans,
                    MAX(score) AS max_score,
                    MAX(created_at) AS last_event_at
                FROM moderation_events
                WHERE user_id = ?
                """,
                (user_id,),
            )
            events_row = await cursor.fetchone()
        return {
            "messages": int(messages_row[0] or 0) if messages_row else 0,
            "flagged": int(events_row[0] or 0) if events_row else 0,
            "reviews": int(events_row[1] or 0) if events_row else 0,
            "deletions": int(events_row[2] or 0) if events_row else 0,
            "bans": int(events_row[3] or 0) if events_row else 0,
            "max_score": int(events_row[4] or 0) if events_row else 0,
            "last_event_at": int(events_row[5]) if events_row and events_row[5] else None,
        }

    async def recent_events(self, chat_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        safe_limit = max(1, min(limit, 50))
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT * FROM moderation_events
                WHERE chat_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (chat_id, safe_limit),
            )
            rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def report_events(self, chat_id: int) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT * FROM moderation_events
                WHERE chat_id = ?
                ORDER BY created_at DESC, id DESC
                """,
                (chat_id,),
            )
            rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def create_pending_action(
        self,
        chat_id: int,
        chat_title: str,
        user_id: int,
        message_id: int,
        full_name: str,
        username: str,
        message_text: str,
        decision: ModerationDecision,
        is_test: bool = False,
    ) -> int:
        reasons = [
            {"code": signal.code, "points": signal.points, "detail": signal.detail}
            for signal in decision.signals
        ]
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """
                INSERT INTO pending_actions(
                    chat_id, chat_title, user_id, message_id, full_name, username,
                    message_text, score, reasons_json, is_test, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chat_id,
                    chat_title[:255],
                    user_id,
                    message_id,
                    full_name[:255],
                    username[:64],
                    message_text[:1000],
                    decision.score,
                    json.dumps(reasons, ensure_ascii=False),
                    1 if is_test else 0,
                    int(time.time()),
                ),
            )
            await db.commit()
            return int(cursor.lastrowid)

    async def get_pending_action(self, action_id: int) -> Dict[str, Any]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM pending_actions WHERE id = ?", (action_id,)
            )
            row = await cursor.fetchone()
        return dict(row) if row else {}

    async def claim_pending_action(self, action_id: int, admin_id: int) -> bool:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """
                UPDATE pending_actions
                SET status = 'processing', decided_by = ?, decided_at = ?
                WHERE id = ? AND status = 'pending'
                """,
                (admin_id, int(time.time()), action_id),
            )
            await db.commit()
            return cursor.rowcount == 1

    async def finalize_pending_action(
        self, action_id: int, status: str, result: str
    ) -> None:
        allowed = {"approved", "rejected", "failed"}
        if status not in allowed:
            raise ValueError("Noto'g'ri pending action status")
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                UPDATE pending_actions
                SET status = ?, result = ?, decided_at = ?
                WHERE id = ? AND status = 'processing'
                """,
                (status, result[:1000], int(time.time()), action_id),
            )
            await db.commit()

    async def upsert_managed_chat(
        self, chat_id: int, title: str, username: str = "", active: bool = True
    ) -> None:
        now = int(time.time())
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT INTO managed_chats(
                    chat_id, title, username, active, added_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(chat_id) DO UPDATE SET
                    title = excluded.title,
                    username = excluded.username,
                    active = excluded.active,
                    updated_at = excluded.updated_at
                """,
                (
                    chat_id,
                    title[:255],
                    username[:64],
                    1 if active else 0,
                    now,
                    now,
                ),
            )
            await db.commit()

    async def list_managed_chats(self) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT * FROM managed_chats
                WHERE active = 1
                ORDER BY title COLLATE NOCASE, chat_id
                """
            )
            rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_managed_chat(self, chat_id: int) -> Dict[str, Any]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM managed_chats WHERE chat_id = ?",
                (chat_id,),
            )
            row = await cursor.fetchone()
        return dict(row) if row else {}

    async def set_managed_chat_active(self, chat_id: int, active: bool) -> bool:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """
                UPDATE managed_chats
                SET active = ?, updated_at = ?
                WHERE chat_id = ?
                """,
                (1 if active else 0, int(time.time()), chat_id),
            )
            await db.commit()
            return cursor.rowcount == 1

    async def set_selected_chat(self, admin_id: int, chat_id: int) -> bool:
        now = int(time.time())
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                "SELECT 1 FROM managed_chats WHERE chat_id = ? AND active = 1",
                (chat_id,),
            )
            if not await cursor.fetchone():
                return False
            await db.execute(
                """
                INSERT INTO admin_preferences(admin_id, selected_chat_id, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(admin_id) DO UPDATE SET
                    selected_chat_id = excluded.selected_chat_id,
                    updated_at = excluded.updated_at
                """,
                (admin_id, chat_id, now),
            )
            await db.commit()
        return True

    async def get_selected_chat_id(
        self, admin_id: int, fallback_chat_id: Optional[int] = None
    ) -> Optional[int]:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """
                SELECT p.selected_chat_id
                FROM admin_preferences p
                JOIN managed_chats c ON c.chat_id = p.selected_chat_id
                WHERE p.admin_id = ? AND c.active = 1
                """,
                (admin_id,),
            )
            row = await cursor.fetchone()
            if row:
                return int(row[0])
            if fallback_chat_id is not None:
                cursor = await db.execute(
                    "SELECT 1 FROM managed_chats WHERE chat_id = ? AND active = 1",
                    (fallback_chat_id,),
                )
                if await cursor.fetchone():
                    return int(fallback_chat_id)
            cursor = await db.execute(
                "SELECT chat_id FROM managed_chats WHERE active = 1 ORDER BY added_at LIMIT 2"
            )
            rows = await cursor.fetchall()
        if len(rows) == 1:
            return int(rows[0][0])
        return None
