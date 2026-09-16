import asyncio
import types
import unittest
from unittest.mock import AsyncMock

from izoh_posbon.profile import ProfileLoader


class ProfileLoaderTests(unittest.IsolatedAsyncioTestCase):
    async def test_loads_bio_personal_channel_and_recent_posts(self) -> None:
        personal_chat = types.SimpleNamespace(
            id=-100123,
            title="34w53",
            username=None,
        )
        private_chat = types.SimpleNamespace(
            bio="Mening maxfiy videolarim shu yerda 🔞 @example_bot",
            personal_chat=personal_chat,
        )
        full_channel = types.SimpleNamespace(
            title="34w53",
            username="example_channel",
            description="Maxfiy videolar",
        )
        recent_message = types.SimpleNamespace(
            text="Ushbu videoni bosing va tomosha qiling",
            caption=None,
            chat=personal_chat,
        )
        bot = AsyncMock()
        bot.get_chat = AsyncMock(side_effect=[private_chat, full_channel])
        bot.get_user_profile_photos = AsyncMock(
            return_value=types.SimpleNamespace(photos=[])
        )
        bot.return_value = [recent_message]
        user = types.SimpleNamespace(
            id=42,
            full_name="Madina Fayziyeva",
            username=None,
        )

        profile = await ProfileLoader().load(bot, user)

        self.assertEqual(profile.bio, private_chat.bio)
        self.assertEqual(profile.personal_channel_id, -100123)
        self.assertEqual(profile.personal_channel_title, "34w53")
        self.assertEqual(profile.personal_channel_username, "example_channel")
        self.assertEqual(profile.personal_channel_description, "Maxfiy videolar")
        self.assertIn("Ushbu videoni", profile.personal_channel_recent_text)

    async def test_concurrent_messages_share_one_profile_request(self) -> None:
        private_chat = types.SimpleNamespace(bio="", personal_chat=None)
        bot = AsyncMock()
        bot.get_chat = AsyncMock(return_value=private_chat)
        bot.get_user_profile_photos = AsyncMock(
            return_value=types.SimpleNamespace(photos=[])
        )
        bot.return_value = []
        user = types.SimpleNamespace(id=77, full_name="Test User", username=None)
        loader = ProfileLoader()

        first, second = await asyncio.gather(
            loader.load(bot, user),
            loader.load(bot, user),
        )

        self.assertIs(first, second)
        bot.get_chat.assert_awaited_once_with(77)
        bot.get_user_profile_photos.assert_awaited_once_with(77, limit=5)


if __name__ == "__main__":
    unittest.main()
