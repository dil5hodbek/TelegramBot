import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from izoh_posbon.models import ModerationAction, ModerationContext, ProfileSnapshot, Signal
from izoh_posbon.moderation import (
    HeuristicChecker,
    ModerationEngine,
    OpenAIModerationChecker,
    PROFANITY_VARIANTS,
    PROHIBITED_EMOJI_COMBINATIONS,
    PROHIBITED_EMOJI_SINGLES,
    contains_dangerous_file_link,
    is_dangerous_file_name,
    prohibited_emoji_count,
)


class HeuristicCheckerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.checker = HeuristicChecker()

    def score(
        self,
        text: str,
        bio: str = "",
        duplicate_count: int = 0,
        personal_channel_title: str = "",
        personal_channel_username: str = "",
        personal_channel_description: str = "",
        personal_channel_recent_text: str = "",
    ) -> int:
        context = ModerationContext(
            text=text,
            profile=ProfileSnapshot(
                user_id=1,
                full_name="Test User",
                username="test_user",
                bio=bio,
                personal_channel_title=personal_channel_title,
                personal_channel_username=personal_channel_username,
                personal_channel_description=personal_channel_description,
                personal_channel_recent_text=personal_channel_recent_text,
            ),
            duplicate_count=duplicate_count,
        )
        return sum(signal.points for signal in self.checker.signals(context))

    def test_screenshot_spam_template_is_deleted(self) -> None:
        score = self.score("Senga qarab bugungi obraz ma'qulmi? 🤍")
        self.assertGreaterEqual(score, 60)

    def test_normal_comment_is_allowed(self) -> None:
        score = self.score("Rahmat, dars juda foydali bo'ldi!")
        self.assertLess(score, 35)

    def test_adult_bio_and_link_is_high_risk(self) -> None:
        score = self.score("Salom", bio="18+ private: https://example.com")
        self.assertGreaterEqual(score, 55)

    def test_duplicate_message_adds_risk(self) -> None:
        score = self.score("Menga shaxsiyga yoz", duplicate_count=1)
        self.assertGreaterEqual(score, 60)

    def test_scam_promise_with_link_is_deleted(self) -> None:
        score = self.score(
            "100% kafolatlangan daromad, hozir https://example.com orqali qo'shiling"
        )
        self.assertGreaterEqual(score, 60)

    def test_adult_profile_name_is_flagged(self) -> None:
        context = ModerationContext(
            text="Salom",
            profile=ProfileSnapshot(user_id=1, full_name="18+ private", username="user"),
        )
        signals = self.checker.signals(context)
        self.assertIn("adult_name", {signal.code for signal in signals})

    def test_uzbek_profanity_reaches_delete_threshold(self) -> None:
        for text in (
            "Haromi",
            "Haromijon",
            "Ko't ekansiz",
            "Ahmoqsan",
            "Jalab",
            "Dalbayob",
            "dalban",
            "dalbayop",
            "Zaybal qildiz",
            "zaybl",
            "gandini",
            "gandingni",
            "dinnnaaxuy",
        ):
            with self.subTest(text=text):
                self.assertGreaterEqual(self.score(text), 60)

    def test_obfuscated_profanity_is_detected(self) -> None:
        for text in ("s.u.k.a", "h a r o m i", "n@xuy", "bl****t", "bl***"):
            with self.subTest(text=text):
                self.assertGreaterEqual(self.score(text), 60)

    def test_every_explicit_profanity_variant_is_detected(self) -> None:
        for label, variants in PROFANITY_VARIANTS:
            for text in variants:
                with self.subTest(label=label, text=text):
                    self.assertGreaterEqual(self.score(text), 60)

    def test_innocent_similar_words_are_not_flagged(self) -> None:
        for text in (
            "Harorat bugun yuqori",
            "Kottej juda chiroyli",
            "Mol go'shti",
            "Salom, ishlaringiz yaxshimi?",
            "Hammasi yaxshi",
            "Amaliyot darsi boshlandi",
            "Siklon yaqinlashmoqda",
            "Musiqa juda yoqimli",
            "BL — bo'lim qisqartmasi",
        ):
            with self.subTest(text=text):
                self.assertLess(self.score(text), 35)

    def test_spam_profile_bio_with_private_video_destination_is_high_risk(self) -> None:
        score = self.score(
            "Salom",
            bio="Mening maxfiy videolarim shu yerda 👇 🔞 @MxxxM342313_bot",
        )
        self.assertGreaterEqual(score, 85)

    def test_personal_channel_recent_spam_post_is_flagged(self) -> None:
        score = self.score(
            "Salom",
            personal_channel_title="34w53",
            personal_channel_recent_text=(
                "Ushbu videoni diqqat bilan bosing va tomosha qiling 👇👇👇💦"
            ),
        )
        self.assertGreaterEqual(score, 35)

    def test_normal_personal_channel_is_not_flagged(self) -> None:
        score = self.score(
            "Salom",
            personal_channel_title="Akmalning texnologiya blogi",
            personal_channel_username="akmal_blog",
            personal_channel_description="Dasturlash va texnologiya haqida",
            personal_channel_recent_text="Python bo'yicha yangi dars e'lon qilindi",
        )
        self.assertLess(score, 35)

    def test_prohibited_emoji_and_sticker_counter(self) -> None:
        expected_singles = {
            "🍆", "🍑", "🍌", "🌭", "🌶", "🥕", "🍒", "🍈", "🥜",
            "🥥", "🍩", "🍯", "🖕", "👅", "👄", "💋", "💦", "🕳",
            "👉", "🤏", "🥵", "😈", "😏", "🤤", "🤬", "👿", "💢",
            "💩", "🚽", "🧻", "🗑", "🤡", "🐓", "🐖", "🐕", "🫏",
            "🐐", "🐍", "🐀", "🪳", "🫦", "🔞", "🛏", "🚫", "🧠",
            "❌", "🦂", "☠", "🤢", "🤮", "🥴",
        }
        self.assertEqual(set(PROHIBITED_EMOJI_SINGLES), expected_singles)
        for emoji in PROHIBITED_EMOJI_SINGLES:
            with self.subTest(emoji=emoji):
                self.assertEqual(prohibited_emoji_count(emoji), 1)
        for combination in PROHIBITED_EMOJI_COMBINATIONS:
            with self.subTest(combination=combination):
                self.assertEqual(prohibited_emoji_count(combination), 1)
        self.assertEqual(prohibited_emoji_count("🍆 🍑 🍌 🌭"), 4)
        self.assertEqual(prohibited_emoji_count("🖕🏽"), 1)
        self.assertEqual(prohibited_emoji_count("🤢🤮🥴"), 3)
        self.assertEqual(prohibited_emoji_count("✅ Rahmat!"), 0)
        self.assertEqual(prohibited_emoji_count("🥒 👌 ✊ 😉 😡 🔥"), 0)

    def test_dangerous_file_names_and_links_require_final_extension(self) -> None:
        for value in (
            "virus.apk",
            "APP.XAPK",
            "bundle.apks",
            "setup.exe",
            "installer.msi",
            "program.dmg",
            "run.bat",
            "start.cmd",
            "screen.scr",
        ):
            with self.subTest(value=value):
                self.assertTrue(is_dangerous_file_name(value))
                self.assertTrue(contains_dangerous_file_link("https://host/" + value))
        self.assertFalse(is_dangerous_file_name("program.apk.zip"))
        self.assertFalse(contains_dangerous_file_link("https://host/program.apk.zip"))
        self.assertFalse(is_dangerous_file_name("archive.zip"))


class OpenAIProfileModerationTests(unittest.IsolatedAsyncioTestCase):
    async def test_profile_photo_is_moderated_separately_from_name_and_bio(self) -> None:
        checker = OpenAIModerationChecker("test-key", enabled=True, ttl_seconds=3600)
        checker._moderate = AsyncMock(
            side_effect=[
                ([], {}),
                ([Signal("ai_sexual_high_profile_photo", 70, "AI: kuchli 18+ profil rasmi")], {"sexual": 0.9}),
            ]
        )
        context = ModerationContext(
            text="Oddiy izoh",
            profile=ProfileSnapshot(
                user_id=1,
                full_name="Odil Karimov",
                username="odil",
                bio="",
                photo_bytes=b"fake-jpeg",
            ),
        )

        signals, categories = await checker._check_profile(context)

        self.assertEqual(signals[0].code, "ai_sexual_high_profile_photo")
        self.assertEqual(categories["sexual"], 0.9)
        calls = checker._moderate.await_args_list
        self.assertEqual(calls[0].kwargs["source"], "profile_text")
        self.assertIsNone(calls[0].kwargs["image_bytes"])
        self.assertEqual(calls[1].kwargs["source"], "profile_photo_1")
        self.assertEqual(calls[1].kwargs["text"], "")
        self.assertEqual(calls[1].kwargs["image_bytes"], b"fake-jpeg")

    async def test_multiple_profile_photos_are_checked_separately(self) -> None:
        checker = OpenAIModerationChecker("test-key", enabled=True, ttl_seconds=3600)
        checker._moderate = AsyncMock(return_value=([], {}))
        context = ModerationContext(
            text="",
            profile=ProfileSnapshot(
                user_id=2,
                full_name="Test",
                photo_samples=(b"first", b"second", b"third"),
            ),
        )

        await checker._check_profile(context)

        calls = checker._moderate.await_args_list
        self.assertEqual(len(calls), 4)
        self.assertEqual(calls[1].kwargs["source"], "profile_photo_1")
        self.assertEqual(calls[2].kwargs["source"], "profile_photo_2")
        self.assertEqual(calls[3].kwargs["source"], "profile_photo_3")

    async def test_ai_rate_limit_keeps_local_moderation_available(self) -> None:
        checker = OpenAIModerationChecker(
            "test-key",
            enabled=True,
            ttl_seconds=3600,
            user_limit=1,
            user_window_seconds=60,
        )
        checker._moderate = AsyncMock(return_value=([], {"sexual": 0.0}))
        context = ModerationContext(
            text="Oddiy xabar",
            chat_id=-100,
            profile=ProfileSnapshot(user_id=9, full_name="Test"),
        )

        first = await checker.signals(context)
        second = await checker.signals(context)

        self.assertEqual(first[1]["sexual"], 0.0)
        self.assertEqual(second, ([], {}))

    async def test_concurrent_messages_share_one_ai_profile_check(self) -> None:
        checker = OpenAIModerationChecker("test-key", enabled=True, ttl_seconds=3600)
        checker._check_profile = AsyncMock(return_value=([], {"sexual": 0.0}))
        context = ModerationContext(
            text="",
            chat_id=-100,
            profile=ProfileSnapshot(user_id=15, full_name="Test User"),
        )

        await asyncio.gather(
            checker.signals(context),
            checker.signals(context),
        )

        checker._check_profile.assert_awaited_once_with(context)

    def test_malware_and_learned_patterns_are_high_risk(self) -> None:
        checker = HeuristicChecker()
        malware = checker.signals(
            ModerationContext(
                text="Salom",
                profile=ProfileSnapshot(
                    user_id=3,
                    full_name="Test",
                    bio="Dasturni example.com/update.apk dan oling",
                ),
            )
        )
        learned = checker.signals(
            ModerationContext(
                text="Maxsus yashirin taklif shu yerda",
                profile=ProfileSnapshot(user_id=3, full_name="Test"),
                learned_patterns=("yashirin taklif",),
            )
        )

        self.assertIn("malware_bio_link", {item.code for item in malware})
        self.assertIn("learned_spam_pattern", {item.code for item in learned})

    def test_coordinated_message_is_only_a_supporting_signal(self) -> None:
        signals = HeuristicChecker().signals(
            ModerationContext(
                text="Hamma shu bir xil uzun xabarni yubordi",
                profile=ProfileSnapshot(user_id=4, full_name="Test"),
                coordinated_user_count=3,
            )
        )
        coordinated = next(item for item in signals if item.code == "coordinated_spam")
        self.assertEqual(coordinated.points, 15)


class ModerationDecisionTests(unittest.IsolatedAsyncioTestCase):
    def make_engine(self) -> ModerationEngine:
        settings = SimpleNamespace(
            openai_api_key=None,
            openai_moderation_enabled=False,
            profile_cache_ttl_seconds=3600,
            review_threshold=35,
            delete_threshold=60,
            ban_threshold=85,
        )
        return ModerationEngine(settings)

    async def test_repeated_greeting_alone_is_allowed(self) -> None:
        context = ModerationContext(
            text="Salom",
            profile=ProfileSnapshot(user_id=1, full_name="Oddiy User"),
            duplicate_count=5,
            seconds_after_post=10,
        )

        decision = await self.make_engine().evaluate(context)

        self.assertEqual(decision.action, ModerationAction.ALLOW)
        self.assertTrue(decision.signals)

    async def test_many_users_same_contest_answer_is_allowed(self) -> None:
        context = ModerationContext(
            text="Ovoz yaxshi eshitilyapti",
            profile=ProfileSnapshot(user_id=1, full_name="Oddiy User"),
            coordinated_user_count=100,
        )

        decision = await self.make_engine().evaluate(context)

        self.assertEqual(decision.action, ModerationAction.ALLOW)
        self.assertIn("coordinated_spam", {item.code for item in decision.signals})

    async def test_arbitrary_repeated_participation_message_is_allowed(self) -> None:
        context = ModerationContext(
            text="Bugungi grant uchun arizamni qoldirdim",
            profile=ProfileSnapshot(user_id=2, full_name="Oddiy User"),
            duplicate_count=20,
            coordinated_user_count=100,
            seconds_after_post=5,
        )

        decision = await self.make_engine().evaluate(context)

        self.assertEqual(decision.action, ModerationAction.ALLOW)
        self.assertTrue(decision.signals)

    async def test_repeated_suspicious_text_still_triggers(self) -> None:
        context = ModerationContext(
            text="Menga shaxsiyga yoz",
            profile=ProfileSnapshot(user_id=1, full_name="Shubhali User"),
            duplicate_count=1,
        )

        decision = await self.make_engine().evaluate(context)

        self.assertNotEqual(decision.action, ModerationAction.ALLOW)

    async def test_local_fast_path_detects_profanity_without_ai(self) -> None:
        context = ModerationContext(
            text="s.i.k.t.i.r",
            profile=ProfileSnapshot(user_id=1, full_name="Oddiy User"),
        )

        decision = self.make_engine().evaluate_local(context)

        self.assertEqual(decision.action, ModerationAction.DELETE)
        self.assertFalse(decision.ai_categories)


if __name__ == "__main__":
    unittest.main()
