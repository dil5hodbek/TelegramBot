import tempfile
import unittest
from pathlib import Path

from izoh_posbon.models import ModerationAction, ModerationDecision, Signal
from izoh_posbon.storage import Storage


class StorageTests(unittest.IsolatedAsyncioTestCase):
    async def test_duplicate_and_event_are_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = Storage(Path(temp_dir) / "test.db", duplicate_window_seconds=3600)
            await storage.initialize()
            self.assertEqual(await storage.duplicate_count(10, "bir xil xabar"), 0)

            await storage.record_message(-100, 10, "bir xil xabar")
            self.assertEqual(await storage.duplicate_count(10, "bir xil xabar"), 1)

            decision = ModerationDecision(
                score=65,
                action=ModerationAction.DELETE,
                signals=[Signal("known_spam", 65, "test")],
            )
            await storage.record_event(-100, 10, 99, "bir xil xabar", decision)
            stats = await storage.user_stats(10)
            self.assertEqual(stats["messages"], 1)
            self.assertEqual(stats["deletions"], 1)
            self.assertEqual(stats["max_score"], 65)
            events = await storage.report_events(-100)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["message_id"], 99)

            pending_id = await storage.create_pending_action(
                chat_id=-100,
                chat_title="Test",
                user_id=10,
                message_id=99,
                full_name="Test User",
                username="test_user",
                message_text="bir xil xabar",
                decision=decision,
                is_test=True,
            )
            pending = await storage.get_pending_action(pending_id)
            self.assertEqual(pending["status"], "pending")
            self.assertEqual(pending["is_test"], 1)
            self.assertTrue(await storage.claim_pending_action(pending_id, 5457999176))
            self.assertFalse(await storage.claim_pending_action(pending_id, 5457999176))
            await storage.finalize_pending_action(pending_id, "approved", "test ok")
            pending = await storage.get_pending_action(pending_id)
            self.assertEqual(pending["status"], "approved")

    async def test_managed_groups_and_admin_selection(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = Storage(Path(temp_dir) / "test.db", duplicate_window_seconds=3600)
            await storage.initialize()
            await storage.upsert_managed_chat(-100, "B guruhi")
            await storage.upsert_managed_chat(-200, "A guruhi", "a_guruh")

            chats = await storage.list_managed_chats()
            self.assertEqual([chat["chat_id"] for chat in chats], [-200, -100])
            self.assertEqual(
                await storage.get_selected_chat_id(5457999176, fallback_chat_id=-100),
                -100,
            )
            self.assertTrue(await storage.set_selected_chat(5457999176, -200))
            self.assertEqual(
                await storage.get_selected_chat_id(5457999176, fallback_chat_id=-100),
                -200,
            )

            await storage.upsert_managed_chat(-200, "A guruhi", active=False)
            self.assertEqual(
                await storage.get_selected_chat_id(5457999176, fallback_chat_id=-100),
                -100,
            )
            self.assertFalse(await storage.set_selected_chat(5457999176, -999))

            await storage.upsert_managed_chat(-300, "Begona guruh")
            self.assertEqual((await storage.get_managed_chat(-300))["active"], 1)
            self.assertTrue(await storage.set_managed_chat_active(-300, False))
            self.assertEqual((await storage.get_managed_chat(-300))["active"], 0)

            self.assertIsNone(await storage.get_state("update_notice"))
            await storage.set_state("update_notice", "v1")
            self.assertEqual(await storage.get_state("update_notice"), "v1")
            await storage.set_state("update_notice", "v2")
            self.assertEqual(await storage.get_state("update_notice"), "v2")

            self.assertEqual(
                await storage.record_emoji_violation(-100, 99),
                1,
            )
            self.assertEqual(
                await storage.record_emoji_violation(-100, 99),
                2,
            )
            db_stats = await storage.database_stats()
            self.assertEqual(db_stats["emoji_violations"], 2)
            await storage.clear_emoji_violations(-100, 99)
            self.assertEqual(
                await storage.record_emoji_violation(-100, 99),
                1,
            )

            self.assertEqual(await storage.record_link_violation(-100, 99), 1)

            await storage.record_bot_message(-100, 500, 10)
            await storage.record_bot_message(-100, 500, 11)
            await storage.record_bot_message(-100, 500, 12)
            await storage.record_bot_message(-100, 600, 13)
            self.assertEqual(
                set(await storage.tracked_bot_user_ids(-100)),
                {500, 600},
            )
            self.assertEqual(
                await storage.recent_bot_message_ids(-100, 500, 2),
                [12, 11],
            )
            await storage.remove_bot_message_records(-100, [12, 11])
            self.assertEqual(
                await storage.recent_bot_message_ids(-100, 500, 10),
                [10],
            )
            self.assertEqual(await storage.record_link_violation(-100, 99), 2)
            db_stats = await storage.database_stats()
            self.assertEqual(db_stats["link_violations"], 2)
            await storage.clear_link_violations(-100, 99)
            self.assertEqual(await storage.record_link_violation(-100, 99), 1)

    async def test_enhanced_audit_and_learned_patterns(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = Storage(Path(temp_dir) / "test.db", duplicate_window_seconds=3600)
            await storage.initialize()

            for user_id in (10, 20):
                await storage.record_message(-100, user_id, "bir xil uzun spam xabari")
            self.assertEqual(
                await storage.coordinated_user_count(
                    -100, 30, "bir xil uzun spam xabari", 120
                ),
                3,
            )

            pattern_id = await storage.add_learned_pattern(
                -100, "maxfiy taklif", 5457999176
            )
            patterns = await storage.learned_patterns(-100)
            self.assertEqual(patterns[0]["id"], pattern_id)
            self.assertTrue(await storage.disable_learned_pattern(pattern_id, -100))

            decision = ModerationDecision(
                score=85,
                action=ModerationAction.BAN,
                signals=[Signal("test", 85, "test sababi")],
                ai_categories={"sexual": 0.9},
            )
            await storage.record_profile_check(
                -100, 30, "Test User", "test", "bio", 2, decision
            )
            await storage.record_ai_usage(
                -100, 30, "openai", "omni-moderation-latest", {"sexual": 0.9}
            )
            await storage.record_blocked_user(
                -100, 30, "Test User", "test", "test sababi"
            )
            stats = await storage.database_stats()
            self.assertEqual(stats["profile_checks"], 1)
            self.assertEqual(stats["ai_usage"], 1)
            self.assertEqual(stats["blocked_users"], 1)
            await storage.mark_unblocked_user(-100, 30, 5457999176)


if __name__ == "__main__":
    unittest.main()
