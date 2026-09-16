import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import (
    BotCommand,
    BotCommandScopeChat,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllPrivateChats,
)

from .config import Settings
from .handlers import create_router
from .moderation import ModerationEngine
from .profile import ProfileLoader
from .release_notes import deployment_fingerprint, render_update_notice
from .storage import Storage


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        stream=sys.stdout,
    )
    settings = Settings.from_env()
    storage = Storage(
        settings.database_path,
        settings.duplicate_window_seconds,
        settings.data_retention_days,
    )
    await storage.initialize()

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher()
    dispatcher.include_router(
        create_router(
            settings,
            storage,
            ProfileLoader(
                settings.profile_cache_ttl_seconds,
                settings.profile_photo_limit,
            ),
            ModerationEngine(settings),
        )
    )

    me = await bot.get_me()
    private_commands = [
        BotCommand(command="start", description="Bot haqida va buyruqlar"),
        BotCommand(command="stats", description="Shaxsiy statistikangiz"),
    ]
    group_commands = [
        BotCommand(command="status", description="Bot holati (admin)"),
    ]
    admin_commands = [
        BotCommand(command="start", description="Admin panel va bot haqida"),
        BotCommand(command="stats", description="Shaxsiy statistikangiz"),
        BotCommand(command="groups", description="Boshqariladigan guruhlar"),
        BotCommand(command="status", description="Bot holati va huquqlari"),
        BotCommand(command="recent", description="So'nggi spamlar (admin)"),
        BotCommand(command="unban", description="Blokni olib tashlash (admin)"),
        BotCommand(command="report", description="Excel hisobot (admin)"),
        BotCommand(command="dbstats", description="Ma'lumotlar bazasi holati"),
        BotCommand(command="position", description="Avtomatik moderatsiya rejimi"),
        BotCommand(command="leave", description="Botni tanlangan guruhdan chiqarish"),
        BotCommand(command="del_bot", description="Admin bot xabarlarini tozalash"),
    ]
    limited_admin_commands = [
        BotCommand(command="start", description="Cheklangan admin paneli"),
        BotCommand(command="status", description="Belgilangan guruh holati"),
        BotCommand(command="recent", description="Belgilangan guruhdagi spamlar"),
        BotCommand(command="report", description="Belgilangan guruh Excel hisoboti"),
        BotCommand(command="dbstats", description="Belgilangan guruh bazasi"),
    ]
    if settings.protected_chat_id is not None:
        try:
            configured_chat = await bot.get_chat(settings.protected_chat_id)
            await storage.upsert_managed_chat(
                configured_chat.id,
                configured_chat.title or str(configured_chat.id),
                configured_chat.username or "",
                active=True,
            )
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "Sozlangan guruh ro'yxatga olinmadi chat=%s: %s",
                settings.protected_chat_id,
                exc,
            )
    await bot.set_my_commands(private_commands, scope=BotCommandScopeAllPrivateChats())
    await bot.set_my_commands(group_commands, scope=BotCommandScopeAllGroupChats())
    await bot.set_my_commands(private_commands)
    for admin_id in settings.admin_ids:
        try:
            await bot.set_my_commands(
                admin_commands,
                scope=BotCommandScopeChat(chat_id=admin_id),
            )
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "Admin command menyusi o'rnatilmadi user=%s: %s", admin_id, exc
            )
    if settings.limited_admin_id not in settings.admin_ids:
        try:
            await bot.set_my_commands(
                limited_admin_commands,
                scope=BotCommandScopeChat(chat_id=settings.limited_admin_id),
            )
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "Cheklangan admin menyusi o'rnatilmadi user=%s: %s",
                settings.limited_admin_id,
                exc,
            )
    fingerprint = deployment_fingerprint()
    update_notice = render_update_notice(fingerprint)
    for admin_id in settings.admin_ids:
        state_key = f"admin_update_notice:{admin_id}"
        if await storage.get_state(state_key) == fingerprint:
            continue
        try:
            await bot.send_message(admin_id, update_notice)
            await storage.set_state(state_key, fingerprint)
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "Yangilanish xabari yuborilmadi admin=%s: %s", admin_id, exc
            )
    logging.getLogger(__name__).info(
        "@%s ishga tushdi. Rejim=%s, AI=%s",
        me.username,
        "APPROVAL_TEST" if settings.dry_run else "AUTOMATIC",
        "ON" if settings.openai_api_key and settings.openai_moderation_enabled else "OFF",
    )
    try:
        # Oldin webhook ishlatilgan bo'lsa long polling bilan to'qnashmasin.
        await bot.delete_webhook(drop_pending_updates=False)
        await dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types())
    finally:
        await bot.session.close()
