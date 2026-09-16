import asyncio
import logging
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from aiohttp import web as aioweb

from .core import copy, groups, patterns, release, retention, stats, usage, watchlist
from .core.config import BOT_TOKEN, DATABASE_URL, ADMIN_TELEGRAM_IDS, KEY_ENCRYPTION_SECRET, PORT
from .handlers.profile_checker import register_profile_handlers
from .handlers.spam_detector import register_spam_handlers
from .handlers.admin_notifier import register_admin_handlers, send_to_admins
from .web import build_app

logging.basicConfig(level=logging.INFO)

try:
    VERSION = (Path(__file__).resolve().parents[1] / "VERSION").read_text().strip()
except Exception:
    VERSION = "?"


async def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN is not set in environment variables")
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL is not set in environment variables")
    if not KEY_ENCRYPTION_SECRET:
        logging.warning(
            "KEY_ENCRYPTION_SECRET not set — groups can't store keys, so AI "
            "moderation is disabled everywhere (regex layer still runs)")

    patterns.reload()   # load seed + learned patterns
    groups.reload()     # load the group allow-list
    watchlist.reload()  # load admin-flagged suspicious accounts

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    # Order matters: profile (new_chat_members) and admin commands (/enable etc.)
    # must run before the broad group handler, which else consumes them.
    register_profile_handlers(dp)
    register_admin_handlers(dp)
    register_spam_handlers(dp)

    # Set command menu + profile description (per-locale: Uzbek default, English for en).
    try:
        await bot.set_my_commands([BotCommand(command=c, description=d) for c, d in copy.COMMANDS_UZ])
        await bot.set_my_commands([BotCommand(command=c, description=d) for c, d in copy.COMMANDS_EN], language_code="en")
        await bot.set_my_description(copy.DESCRIPTION_UZ)
        await bot.set_my_description(copy.DESCRIPTION_EN, language_code="en")
    except Exception as e:
        logging.error(f"Failed to set bot profile: {e}")

    # Start the key-entry web server in the same loop (before polling blocks).
    runner = aioweb.AppRunner(build_app())
    await runner.setup()
    await aioweb.TCPSite(runner, "0.0.0.0", PORT).start()
    logging.info(f"Key-entry web server listening on :{PORT}")

    logging.info("Starting minimal spam protection bot...")
    try:
        await send_to_admins(bot, f"✅ spam-bot v{VERSION} is up and running")
    except Exception as e:
        logging.error(f"Startup notification failed: {e}")
    try:
        await announce_release(bot)
    except Exception as e:
        logging.error(f"Release announcement failed: {e}")  # never block startup
    asyncio.create_task(_retention_loop())
    asyncio.create_task(_daily_report_loop(bot))
    # resolve_used_update_types() ensures chat_join_request (and others) are subscribed
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


async def announce_release(bot) -> None:
    """On a version bump, DM the latest CHANGELOG section to bot admins and the
    admins of every protected group. Best-effort: a DM fails if the recipient
    hasn't started the bot (Telegram privacy) — we log and move on. Gated on the
    stored version so restarts on the same release don't re-send."""
    if release.already_announced(VERSION):
        return
    notes = release.latest_notes_html()  # Telegram HTML — markdown '##'/'- ' don't render
    if not notes:
        return  # no notes -> don't mark, retry on next deploy
    text = f"🚀 <b>spam-bot updated to v{VERSION}</b>\n\n{notes}"

    recipients = {int(x) for x in ADMIN_TELEGRAM_IDS if str(x).lstrip("-").isdigit()}
    for chat_id in groups.allowed_ids():
        try:
            for adm in await bot.get_chat_administrators(chat_id):
                if not adm.user.is_bot:
                    recipients.add(adm.user.id)
        except Exception as e:
            logging.warning(f"Couldn't list admins of {chat_id}: {e}")

    sent = 0
    for uid in recipients:
        try:
            await bot.send_message(chat_id=uid, text=text, parse_mode="HTML",
                                   disable_web_page_preview=True)
            sent += 1
        except Exception as e:
            logging.info(f"Release notes not delivered to {uid}: {e}")
    logging.info(f"Release notes v{VERSION}: delivered to {sent}/{len(recipients)} admins")
    release.mark_announced(VERSION)


async def _retention_loop():
    while True:
        retention.purge_old()
        await asyncio.sleep(86400)


async def send_daily_report(bot) -> None:
    """DM yesterday's token usage: the global, per-group view to the operator, and
    each protected group's own numbers to its admins. Guarded by an app_state date
    key so a restart on the same day doesn't re-send."""
    date_str = usage.tashkent_today_str()
    if usage.already_reported(date_str):
        return
    titles = await stats.resolve_titles(bot, groups.allowed_ids())
    await send_to_admins(bot, stats.report(titles))        # operator: activity + roster
    await send_to_admins(bot, usage.daily_report(None))   # operator: all groups

    start, end = usage.yesterday_bounds_utc()
    for chat_id in groups.allowed_ids():
        rows = usage.summary(start, end, chat_id)
        if not rows:
            continue  # don't ping a group's admins on a zero-usage day
        text = usage.format_window(rows, "Yesterday's token usage")
        try:
            admins = await bot.get_chat_administrators(chat_id)
        except Exception as e:
            logging.warning(f"daily report: couldn't list admins of {chat_id}: {e}")
            continue
        for adm in admins:
            if adm.user.is_bot:
                continue
            try:
                await bot.send_message(adm.user.id, text)
            except Exception as e:
                logging.info(f"daily report not delivered to {adm.user.id}: {e}")
    usage.mark_reported(date_str)


async def _daily_report_loop(bot):
    from .core.config import REPORT_HOUR
    while True:
        await asyncio.sleep(usage.seconds_until_hour(REPORT_HOUR))
        try:
            await send_daily_report(bot)
        except Exception as e:
            logging.error(f"daily report failed: {e}")
        await asyncio.sleep(60)  # clear the trigger minute before recomputing


if __name__ == "__main__":
    asyncio.run(main())
