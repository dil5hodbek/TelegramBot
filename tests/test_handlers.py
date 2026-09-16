import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from izoh_posbon.models import ModerationAction, ModerationDecision, Signal

from izoh_posbon.handlers import (
    _apply_action,
    _dangerous_attachment_names,
    _emoji_violation_decision,
    _group_admin_notice,
    _leave_confirmation,
    _leave_keyboard,
    _automatic_mode_key,
    _del_bot_count_keyboard,
    _is_automatic_mode,
    _is_membership_service_message,
    _link_violation_decision,
    _message_has_link_or_username,
    _parse_positive_user_id,
    _position_confirmation,
    _position_keyboard,
    _send_log,
)


class HandlerMessageTests(unittest.TestCase):
    def test_group_admin_notice_contains_group_and_permissions(self) -> None:
        notice = _group_admin_notice("Test <guruh>", -100123, True, False)

        self.assertIn("Yangi guruh ulandi", notice)
        self.assertIn("Test &lt;guruh&gt;", notice)
        self.assertIn("-100123", notice)
        self.assertIn("Xabar o'chirish huquqi: <b>bor</b>", notice)
        self.assertIn("Bloklash huquqi: <b>yo‘q</b>", notice)

    def test_leave_confirmation_identifies_exact_group(self) -> None:
        text = _leave_confirmation("Begona <guruh>", -100999)
        keyboard = _leave_keyboard(-100999)

        self.assertIn("Begona &lt;guruh&gt;", text)
        self.assertIn("-100999", text)
        self.assertNotIn("🚪", text)
        self.assertEqual(keyboard.inline_keyboard[0][0].text, "✅ Chiqib ketish")
        self.assertEqual(keyboard.inline_keyboard[0][1].text, "❌ Bekor qilish")
        self.assertEqual(
            keyboard.inline_keyboard[0][0].callback_data,
            "group:leave_confirm:-100999",
        )
        self.assertEqual(
            keyboard.inline_keyboard[0][1].callback_data,
            "group:leave_cancel:-100999",
        )

    def test_unban_user_id_parser(self) -> None:
        self.assertEqual(_parse_positive_user_id(" 123456789 "), 123456789)
        self.assertIsNone(_parse_positive_user_id("abc"))
        self.assertIsNone(_parse_positive_user_id("0"))
        self.assertIsNone(_parse_positive_user_id("-12"))

    def test_position_enable_and_disable_confirmation(self) -> None:
        enable_text = _position_confirmation("Test <guruh>", -100555, False)
        enable_keyboard = _position_keyboard(-100555, False)
        self.assertIn("Belgilangan chat: <b>Test &lt;guruh&gt;</b>", enable_text)
        self.assertIn("To'liq huquqni botga bermoqchimisiz?", enable_text)
        self.assertEqual(enable_keyboard.inline_keyboard[0][0].text, "✅ Ha")
        self.assertEqual(
            enable_keyboard.inline_keyboard[0][0].callback_data,
            "position:enable:-100555",
        )

        disable_text = _position_confirmation("Test", -100555, True)
        disable_keyboard = _position_keyboard(-100555, True)
        self.assertIn("To'liq huquqni botdan olmoqchimisiz?", disable_text)
        self.assertEqual(
            disable_keyboard.inline_keyboard[0][0].callback_data,
            "position:disable:-100555",
        )

    def test_position_mode_state_is_per_chat(self) -> None:
        self.assertEqual(_automatic_mode_key(-1001), "automatic_moderation:-1001")
        self.assertEqual(_automatic_mode_key(-1002), "automatic_moderation:-1002")
        self.assertTrue(_is_automatic_mode("1", True))
        self.assertFalse(_is_automatic_mode("0", False))
        self.assertFalse(_is_automatic_mode(None, True))
        self.assertTrue(_is_automatic_mode(None, False))

    def test_emoji_ban_depends_on_messages_not_emoji_amount(self) -> None:
        first_message = _emoji_violation_decision(20, 1)
        third_message = _emoji_violation_decision(1, 3)
        fourth_message = _emoji_violation_decision(1, 4)

        self.assertEqual(first_message.action, ModerationAction.DELETE)
        self.assertEqual(third_message.action, ModerationAction.DELETE)
        self.assertEqual(fourth_message.action, ModerationAction.BAN)

    def test_link_ban_starts_on_fourth_link_message(self) -> None:
        first_message = _link_violation_decision(1)
        third_message = _link_violation_decision(3)
        fourth_message = _link_violation_decision(4)

        self.assertEqual(first_message.action, ModerationAction.DELETE)
        self.assertEqual(third_message.action, ModerationAction.DELETE)
        self.assertEqual(fourth_message.action, ModerationAction.BAN)

    def test_dangerous_telegram_attachment_names_are_found(self) -> None:
        message = SimpleNamespace(
            document=SimpleNamespace(file_name="payload.APK"),
            audio=None,
            video=SimpleNamespace(file_name="normal.mp4"),
            animation=SimpleNamespace(file_name="trick.exe"),
        )

        self.assertEqual(
            _dangerous_attachment_names(message),
            ("payload.APK", "trick.exe"),
        )

    def test_visible_and_hidden_links_or_usernames_are_found(self) -> None:
        for text in (
            "https://example.com/path",
            "tezkor.uz/gov",
            "t.me/asadulo",
            "@sabrina",
            "noma'lum-domen.xyz/taklif",
            "bir nechta example.com va t.me/test_link",
        ):
            with self.subTest(text=text):
                message = SimpleNamespace(
                    text=text,
                    caption=None,
                    entities=None,
                    caption_entities=None,
                )
                self.assertTrue(_message_has_link_or_username(message))

        hidden_link = SimpleNamespace(
            text="Shu yerni bosing",
            caption=None,
            entities=[SimpleNamespace(type=SimpleNamespace(value="text_link"))],
            caption_entities=None,
        )
        self.assertTrue(_message_has_link_or_username(hidden_link))

        normal = SimpleNamespace(
            text="Ovoz yaxshi eshitilyapti",
            caption=None,
            entities=None,
            caption_entities=None,
        )
        self.assertFalse(_message_has_link_or_username(normal))

        # Bo'sh joysiz yozilgan ikki gap domen emas: "edim.Osha", "edi.Agar".
        innocent = SimpleNamespace(
            text="4-o'rinni olgan edim.Osha payt zo'r edi.Agar yana bo'lsa qatnashaman.",
            caption=None,
            entities=None,
            caption_entities=None,
        )
        self.assertFalse(_message_has_link_or_username(innocent))

    def test_join_and_leave_service_messages_are_detected(self) -> None:
        joined = SimpleNamespace(new_chat_members=[SimpleNamespace(id=1)], left_chat_member=None)
        left = SimpleNamespace(new_chat_members=None, left_chat_member=SimpleNamespace(id=1))
        normal = SimpleNamespace(new_chat_members=None, left_chat_member=None)

        self.assertTrue(_is_membership_service_message(joined))
        self.assertTrue(_is_membership_service_message(left))
        self.assertFalse(_is_membership_service_message(normal))

    def test_del_bot_count_keyboard_has_requested_sizes(self) -> None:
        keyboard = _del_bot_count_keyboard(-100555, 777)
        buttons = keyboard.inline_keyboard[0]

        self.assertEqual([item.text for item in buttons], ["1 ta", "5 ta", "10 ta"])
        self.assertEqual(
            [item.callback_data for item in buttons],
            [
                "delbot:count:-100555:777:1",
                "delbot:count:-100555:777:5",
                "delbot:count:-100555:777:10",
            ],
        )

class AutomaticActionTests(unittest.IsolatedAsyncioTestCase):
    async def test_position_force_bypasses_global_dry_run(self) -> None:
        bot = SimpleNamespace(delete_message=AsyncMock())
        message = SimpleNamespace(
            chat=SimpleNamespace(id=-100555),
            message_id=77,
        )
        user = SimpleNamespace(id=123, full_name="Test User", username="test")
        decision = ModerationDecision(
            score=65,
            action=ModerationAction.DELETE,
            signals=[],
        )

        result = await _apply_action(
            bot,
            message,
            user,
            decision,
            SimpleNamespace(dry_run=True),
            force=True,
        )

        bot.delete_message.assert_awaited_once_with(-100555, 77)
        self.assertIn("izoh o'chirildi", result)

    async def test_result_is_sent_to_every_admin_without_log_chat(self) -> None:
        bot = SimpleNamespace(send_message=AsyncMock())
        message = SimpleNamespace(
            chat=SimpleNamespace(id=-100555, title="Test guruhi"),
            message_id=77,
            text="spam xabar",
            caption=None,
        )
        user = SimpleNamespace(id=123, full_name="Test User", username="test")
        decision = ModerationDecision(
            score=90,
            action=ModerationAction.BAN,
            signals=[Signal("spam", 90, "Spam aniqlandi")],
        )
        settings = SimpleNamespace(
            admin_ids=frozenset({1001, 1002}),
            mod_log_chat_id=None,
        )

        await _send_log(bot, message, user, decision, settings, "user bloklandi")

        self.assertEqual(bot.send_message.await_count, 2)
        targets = {call.args[0] for call in bot.send_message.await_args_list}
        self.assertEqual(targets, {1001, 1002})


if __name__ == "__main__":
    unittest.main()
