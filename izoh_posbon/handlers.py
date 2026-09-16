import asyncio
import contextlib
import html
import json
import logging
from datetime import datetime
from typing import Optional

from aiogram import Bot, F, Router
from aiogram.enums import ChatMemberStatus, ChatType, ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    ChatMemberUpdated,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    User,
)

from .config import Settings
from .models import (
    ModerationAction,
    ModerationContext,
    ModerationDecision,
    ProfileSnapshot,
    Signal,
)
from .moderation import (
    EMOJI_BAN_AFTER_COUNT,
    ModerationEngine,
    contains_dangerous_file_link,
    contains_link_or_username,
    is_dangerous_file_name,
    prohibited_emoji_count,
)
from .profile import ProfileLoader
from .report import build_excel_report
from .storage import Storage

logger = logging.getLogger(__name__)


class UnbanFlow(StatesGroup):
    waiting_for_user_id = State()


LINK_BAN_AFTER_COUNT = 3


def _parse_positive_user_id(value: str) -> Optional[int]:
    try:
        user_id = int(value.strip())
    except (TypeError, ValueError):
        return None
    return user_id if user_id > 0 else None


def _pending_prompt(action: dict) -> str:
    try:
        reasons_data = json.loads(action.get("reasons_json") or "[]")
    except (TypeError, json.JSONDecodeError):
        reasons_data = []
    reasons = "\n".join(
        "• " + html.escape(str(item.get("detail") or item.get("code") or ""))
        for item in reasons_data
        if isinstance(item, dict)
    ) or "• Shubhali profil va xabar belgilari"
    username = "@" + action["username"] if action.get("username") else "username yo'q"
    full_name = action.get("full_name") or "Noma'lum"
    message_text = action.get("message_text") or "[matnsiz xabar]"
    test_note = (
        "\n\n🧪 <b>Bu xavfsiz test.</b> Tugmalar ishlashi tekshiriladi, "
        "hech kim bloklanmaydi."
        if action.get("is_test")
        else ""
    )
    return (
        "⚠️ <b>Shubhali profil aniqlandi</b>\n\n"
        f"Profil: <b>{html.escape(full_name)}</b> "
        f"({html.escape(username)})\n"
        f"Guruh: {html.escape(action.get('chat_title') or str(action.get('chat_id')))}\n"
        f"Risk: <b>{action.get('score', 0)}</b>\n\n"
        f"<b>Xabar matni</b>\n“{html.escape(str(message_text)[:600])}”\n\n"
        f"<b>Sabablar</b>\n{reasons}\n\n"
        "Ushbu xabarni o'chirib, profilni guruhdan bloklab qo'yaymi?"
        + test_note
    )


def _pending_keyboard(action_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Ha", callback_data=f"moderate:yes:{action_id}"
                ),
                InlineKeyboardButton(
                    text="❌ Yo'q", callback_data=f"moderate:no:{action_id}"
                ),
            ]
        ]
    )


def _group_admin_notice(
    chat_title: str,
    chat_id: int,
    can_delete: bool,
    can_ban: bool,
) -> str:
    return (
        "✅ <b>Yangi guruh ulandi</b>\n\n"
        "Bot administrator qilindi.\n"
        f"Guruh: <b>{html.escape(chat_title)}</b>\n"
        f"Guruh ID: <code>{chat_id}</code>\n"
        f"Xabar o'chirish huquqi: <b>{'bor' if can_delete else 'yo‘q'}</b>\n"
        f"Bloklash huquqi: <b>{'bor' if can_ban else 'yo‘q'}</b>\n\n"
        "Guruhni boshqarish uchun /groups buyrug'ini bosing."
    )


def _leave_confirmation(chat_title: str, chat_id: int) -> str:
    return (
        "<b>Guruhdan chiqish</b>\n\n"
        f"Guruh: <b>{html.escape(chat_title)}</b>\n"
        f"Guruh ID: <code>{chat_id}</code>\n\n"
        "Bot ushbu guruhdan chiqib, uni boshqariladigan guruhlar ro'yxatidan "
        "olib tashlaydi. Davom etilsinmi?"
    )


def _leave_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Chiqib ketish",
                    callback_data=f"group:leave_confirm:{chat_id}",
                ),
                InlineKeyboardButton(
                    text="❌ Bekor qilish",
                    callback_data=f"group:leave_cancel:{chat_id}",
                ),
            ]
        ]
    )


def _automatic_mode_key(chat_id: int) -> str:
    return f"automatic_moderation:{chat_id}"


def _is_automatic_mode(stored_value: Optional[str], dry_run_default: bool) -> bool:
    if stored_value == "1":
        return True
    if stored_value == "0":
        return False
    return not dry_run_default


def _position_confirmation(
    chat_title: str,
    chat_id: int,
    automatic_enabled: bool,
) -> str:
    question = (
        "To'liq huquqni botdan olmoqchimisiz?"
        if automatic_enabled
        else "To'liq huquqni botga bermoqchimisiz?"
    )
    current_mode = "TO'LIQ AVTOMATIK" if automatic_enabled else "TASDIQLI SINOV"
    return (
        "<b>Moderatsiya rejimi</b>\n\n"
        f"Belgilangan chat: <b>{html.escape(chat_title)}</b>\n"
        f"Guruh ID: <code>{chat_id}</code>\n"
        f"Hozirgi rejim: <b>{current_mode}</b>\n\n"
        f"{question}"
    )


def _position_keyboard(chat_id: int, automatic_enabled: bool) -> InlineKeyboardMarkup:
    action = "disable" if automatic_enabled else "enable"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Ha",
                    callback_data=f"position:{action}:{chat_id}",
                )
            ]
        ]
    )


def _emoji_violation_decision(
    emoji_count: int,
    violation_message_count: int,
) -> ModerationDecision:
    should_ban = violation_message_count > EMOJI_BAN_AFTER_COUNT
    return ModerationDecision(
        score=85 if should_ban else 65,
        action=ModerationAction.BAN if should_ban else ModerationAction.DELETE,
        signals=[
            Signal(
                "prohibited_emoji",
                85 if should_ban else 65,
                "Taqiqlangan emoji/sticker: "
                f"xabarda {emoji_count} ta; qoidabuzar xabarlar jami "
                f"{violation_message_count} ta",
            )
        ],
    )


def _link_violation_decision(violation_message_count: int) -> ModerationDecision:
    should_ban = violation_message_count > LINK_BAN_AFTER_COUNT
    return ModerationDecision(
        score=85 if should_ban else 65,
        action=ModerationAction.BAN if should_ban else ModerationAction.DELETE,
        signals=[
            Signal(
                "user_link_or_username",
                85 if should_ban else 65,
                "Oddiy foydalanuvchi havola yoki @username yubordi; "
                f"havolali xabarlar jami {violation_message_count} ta",
            )
        ],
    )


def _dangerous_attachment_names(message: Message) -> tuple[str, ...]:
    names = []
    for attribute in ("document", "audio", "video", "animation"):
        media = getattr(message, attribute, None)
        file_name = (getattr(media, "file_name", None) or "").strip()
        if file_name and is_dangerous_file_name(file_name):
            names.append(file_name)
    return tuple(names)


def _message_has_link_or_username(message: Message) -> bool:
    text = (getattr(message, "text", None) or getattr(message, "caption", None) or "")
    if contains_link_or_username(text):
        return True
    entities = tuple(getattr(message, "entities", None) or ()) + tuple(
        getattr(message, "caption_entities", None) or ()
    )
    link_entity_types = {"url", "text_link", "mention"}
    return any(
        str(getattr(getattr(entity, "type", None), "value", getattr(entity, "type", "")))
        in link_entity_types
        for entity in entities
    )


def _is_membership_service_message(message: Message) -> bool:
    return bool(
        getattr(message, "new_chat_members", None)
        or getattr(message, "left_chat_member", None)
    )


def _del_bot_count_keyboard(chat_id: int, bot_user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{count} ta",
                    callback_data=f"delbot:count:{chat_id}:{bot_user_id}:{count}",
                )
                for count in (1, 5, 10)
            ]
        ]
    )


def create_router(
    settings: Settings,
    storage: Storage,
    profile_loader: ProfileLoader,
    engine: ModerationEngine,
) -> Router:
    router = Router(name="izoh-posbon")

    async def automatic_mode_enabled(chat_id: int) -> bool:
        stored_value = await storage.get_state(_automatic_mode_key(chat_id))
        return _is_automatic_mode(stored_value, settings.dry_run)

    async def is_admin(
        bot: Bot, chat_id: int, user: User, allow_on_error: bool = False
    ) -> bool:
        if user.id in settings.admin_ids:
            return True
        try:
            member = await bot.get_chat_member(chat_id, user.id)
            return member.status in {
                ChatMemberStatus.CREATOR,
                ChatMemberStatus.ADMINISTRATOR,
            }
        except Exception as exc:
            logger.warning("Admin holati tekshirilmadi user_id=%s: %s", user.id, exc)
            return allow_on_error

    def is_panel_admin(message: Message) -> bool:
        user = message.from_user
        return bool(
            user
            and not message.sender_chat
            and user.id in settings.admin_ids
        )

    def is_limited_admin(message: Message) -> bool:
        user = message.from_user
        return bool(
            user
            and not message.sender_chat
            and user.id == settings.limited_admin_id
            and user.id not in settings.admin_ids
        )

    async def require_private_panel_reader(message: Message) -> bool:
        if message.chat.type != ChatType.PRIVATE:
            await message.answer("Bu buyruq faqat bot bilan private chatda ishlaydi.")
            return False
        if not (is_panel_admin(message) or is_limited_admin(message)):
            await message.answer("Bu buyruq faqat ruxsat etilgan admin uchun.")
            return False
        return True

    async def require_private_panel_admin(message: Message) -> bool:
        if message.chat.type != ChatType.PRIVATE:
            await message.answer("Bu buyruq faqat bot bilan private chatda ishlaydi.")
            return False
        if not is_panel_admin(message):
            await message.answer("Bu buyruq faqat boshqaruvchi admin uchun.")
            return False
        return True

    async def protected_chat_id_or_error(message: Message) -> Optional[int]:
        user = message.from_user
        if not user:
            return None
        if is_limited_admin(message):
            return settings.limited_admin_chat_id
        chat_id = await storage.get_selected_chat_id(
            user.id, fallback_chat_id=settings.protected_chat_id
        )
        if chat_id is None:
            await message.answer(
                "Boshqariladigan guruh tanlanmagan. Avval botni guruhga qo'shing, "
                "keyin private chatda /groups orqali guruhni tanlang."
            )
            return None
        return chat_id

    async def groups_panel(
        admin_id: int,
    ) -> tuple[str, Optional[InlineKeyboardMarkup]]:
        chats = await storage.list_managed_chats()
        selected_chat_id = await storage.get_selected_chat_id(
            admin_id, fallback_chat_id=settings.protected_chat_id
        )
        if not chats:
            return (
                "<b>Guruhlar</b>\n\n"
                "Hali boshqariladigan guruh topilmadi. Botni guruhga qo'shing va "
                "administrator huquqini bering.",
                None,
            )

        buttons = []
        selected_title = "tanlanmagan"
        for chat in chats:
            chat_id = int(chat["chat_id"])
            title = chat.get("title") or str(chat_id)
            if chat_id == selected_chat_id:
                selected_title = title
            prefix = "✅" if chat_id == selected_chat_id else "▫️"
            buttons.append(
                [
                    InlineKeyboardButton(
                        text=f"{prefix} {title}"[:64],
                        callback_data=f"group:select:{chat_id}",
                    )
                ]
            )
        text = (
            "<b>Boshqariladigan guruhlar</b>\n\n"
            f"Tanlangan guruh: <b>{html.escape(selected_title)}</b>\n\n"
            "Guruhni tanlang. /status, /recent, /unban va /report "
            "shu guruh bo'yicha ishlaydi."
        )
        return text, InlineKeyboardMarkup(inline_keyboard=buttons)

    async def send_approval_request(bot: Bot, action_id: int) -> None:
        action = await storage.get_pending_action(action_id)
        if not action:
            return
        for admin_id in settings.admin_ids:
            try:
                await bot.send_message(
                    admin_id,
                    _pending_prompt(action),
                    reply_markup=_pending_keyboard(action_id),
                    parse_mode=ParseMode.HTML,
                )
            except Exception as exc:
                logger.error(
                    "Admin tasdiq so'rovi yuborilmadi admin=%s action=%s: %s",
                    admin_id,
                    action_id,
                    exc,
                )

    @router.callback_query(F.data.startswith("moderate:"))
    async def moderation_callback(callback: CallbackQuery, bot: Bot) -> None:
        user = callback.from_user
        if user.id not in settings.admin_ids:
            await callback.answer("Sizda bu qaror uchun ruxsat yo'q.", show_alert=True)
            return
        try:
            _, choice, raw_action_id = (callback.data or "").split(":", maxsplit=2)
            action_id = int(raw_action_id)
        except (ValueError, AttributeError):
            await callback.answer("Noto'g'ri so'rov.", show_alert=True)
            return

        action = await storage.get_pending_action(action_id)
        if not action or action.get("status") != "pending":
            await callback.answer("Bu so'rov avval ko'rib chiqilgan.", show_alert=True)
            return
        if choice not in {"yes", "no"}:
            await callback.answer("Noto'g'ri tanlov.", show_alert=True)
            return
        if not await storage.claim_pending_action(action_id, user.id):
            await callback.answer("Bu so'rov avval ko'rib chiqilgan.", show_alert=True)
            return

        if choice == "no":
            result = "❌ Yo'q tanlandi. Hech qanday o'zgarish amalga oshirilmadi."
            await storage.finalize_pending_action(action_id, "rejected", result)
        elif action.get("is_test"):
            result = "✅ Ha tugmasi ishladi. Bu test bo'lgani uchun hech kim bloklanmadi."
            await storage.finalize_pending_action(action_id, "approved", result)
        else:
            results = []
            success = False
            try:
                await bot.delete_message(action["chat_id"], action["message_id"])
                results.append("xabar o'chirildi")
                success = True
            except Exception as exc:
                logger.warning("Tasdiqlangan xabar o'chmadi action=%s: %s", action_id, exc)
                results.append("xabarni o'chirishda xato")
            try:
                await bot.ban_chat_member(
                    action["chat_id"], action["user_id"], revoke_messages=True
                )
                results.append("profil bloklandi")
                success = True
            except Exception as exc:
                logger.warning("Tasdiqlangan profil bloklanmadi action=%s: %s", action_id, exc)
                results.append("profilni bloklashda xato")
            else:
                try:
                    reason_items = json.loads(action.get("reasons_json") or "[]")
                except (TypeError, json.JSONDecodeError):
                    reason_items = []
                reason = "; ".join(
                    str(item.get("detail") or item.get("code") or "")
                    for item in reason_items
                    if isinstance(item, dict)
                ) or "Admin tasdiqlagan moderatsiya qarori"
                try:
                    await storage.record_blocked_user(
                        int(action["chat_id"]),
                        int(action["user_id"]),
                        str(action.get("full_name") or ""),
                        str(action.get("username") or ""),
                        reason,
                    )
                except Exception as exc:
                    logger.warning(
                        "Bloklash auditi yozilmadi action=%s: %s", action_id, exc
                    )
            result = ("✅ " if success else "⚠️ ") + "; ".join(results) + "."
            await storage.finalize_pending_action(
                action_id, "approved" if success else "failed", result
            )

        await callback.answer("Qaror qabul qilindi.")
        if callback.message:
            try:
                await callback.message.edit_text(
                    _pending_prompt(action) + "\n\n" + result,
                    reply_markup=None,
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                logger.exception("Tasdiq xabari yangilanmadi action=%s", action_id)

    @router.callback_query(F.data.startswith("group:select:"))
    async def group_select_callback(callback: CallbackQuery) -> None:
        user = callback.from_user
        if user.id not in settings.admin_ids:
            await callback.answer("Bu panel faqat boshqaruvchi admin uchun.", show_alert=True)
            return
        try:
            chat_id = int((callback.data or "").rsplit(":", maxsplit=1)[1])
        except (ValueError, IndexError):
            await callback.answer("Noto'g'ri guruh.", show_alert=True)
            return
        current_chat_id = await storage.get_selected_chat_id(
            user.id, fallback_chat_id=settings.protected_chat_id
        )
        if current_chat_id == chat_id:
            await callback.answer("Bu guruh allaqachon tanlangan.")
            return
        if not await storage.set_selected_chat(user.id, chat_id):
            await callback.answer("Bu guruh faol ro'yxatda yo'q.", show_alert=True)
            return
        text, keyboard = await groups_panel(user.id)
        await callback.answer("Guruh tanlandi.")
        if callback.message:
            await callback.message.edit_text(
                text, reply_markup=keyboard, parse_mode=ParseMode.HTML
            )

    async def show_leave_confirmation(
        chat_id: int,
        send_message,
    ) -> None:
        chat = await storage.get_managed_chat(chat_id)
        if not chat or not bool(chat.get("active")):
            await send_message("Bu guruh faol ro'yxatda topilmadi.")
            return
        title = str(chat.get("title") or chat_id)
        await send_message(
            _leave_confirmation(title, chat_id),
            reply_markup=_leave_keyboard(chat_id),
            parse_mode=ParseMode.HTML,
        )

    @router.callback_query(F.data.startswith("group:leave_cancel:"))
    async def group_leave_cancel_callback(callback: CallbackQuery) -> None:
        if callback.from_user.id not in settings.admin_ids:
            await callback.answer("Bu panel faqat boshqaruvchi admin uchun.", show_alert=True)
            return
        text, keyboard = await groups_panel(callback.from_user.id)
        if callback.message:
            await callback.message.edit_text(
                text, reply_markup=keyboard, parse_mode=ParseMode.HTML
            )
        await callback.answer("Bekor qilindi.")

    @router.callback_query(F.data.startswith("group:leave_confirm:"))
    async def group_leave_confirm_callback(callback: CallbackQuery, bot: Bot) -> None:
        if callback.from_user.id not in settings.admin_ids:
            await callback.answer("Bu panel faqat boshqaruvchi admin uchun.", show_alert=True)
            return
        try:
            chat_id = int((callback.data or "").rsplit(":", maxsplit=1)[1])
        except (ValueError, IndexError):
            await callback.answer("Noto'g'ri guruh.", show_alert=True)
            return
        chat = await storage.get_managed_chat(chat_id)
        if not chat or not bool(chat.get("active")):
            await callback.answer("Bu guruh faol ro'yxatda topilmadi.", show_alert=True)
            return
        title = str(chat.get("title") or chat_id)
        try:
            left = await bot.leave_chat(chat_id)
            if not left:
                raise RuntimeError("Telegram guruhdan chiqishni tasdiqlamadi")
        except Exception as exc:
            logger.warning("Bot guruhdan chiqa olmadi chat=%s: %s", chat_id, exc)
            await callback.answer(
                "Guruhdan chiqib bo'lmadi. Keyinroq qayta urinib ko'ring.",
                show_alert=True,
            )
            return
        await storage.set_managed_chat_active(chat_id, False)
        if callback.message:
            await callback.message.edit_text(
                "✅ <b>Bot guruhdan chiqdi</b>\n\n"
                f"Guruh: <b>{html.escape(title)}</b>\n"
                f"Guruh ID: <code>{chat_id}</code>",
                reply_markup=None,
                parse_mode=ParseMode.HTML,
            )
        await callback.answer("Bot guruhdan chiqdi.")

    @router.callback_query(F.data.startswith("position:"))
    async def position_callback(callback: CallbackQuery, bot: Bot) -> None:
        if callback.from_user.id not in settings.admin_ids:
            await callback.answer("Bu panel faqat boshqaruvchi admin uchun.", show_alert=True)
            return
        try:
            _, action, raw_chat_id = (callback.data or "").split(":", maxsplit=2)
            chat_id = int(raw_chat_id)
        except (ValueError, AttributeError):
            await callback.answer("Noto'g'ri so'rov.", show_alert=True)
            return
        if action not in {"enable", "disable"}:
            await callback.answer("Noto'g'ri amal.", show_alert=True)
            return
        selected_chat_id = await storage.get_selected_chat_id(
            callback.from_user.id,
            fallback_chat_id=settings.protected_chat_id,
        )
        if selected_chat_id != chat_id:
            await callback.answer(
                "Tanlangan guruh o'zgargan. /position buyrug'ini qayta bosing.",
                show_alert=True,
            )
            return
        chat = await storage.get_managed_chat(chat_id)
        if not chat or not bool(chat.get("active")):
            await callback.answer("Bu guruh faol ro'yxatda topilmadi.", show_alert=True)
            return
        enable = action == "enable"
        if enable:
            try:
                me = await bot.get_me()
                member = await bot.get_chat_member(chat_id, me.id)
                can_delete = bool(getattr(member, "can_delete_messages", False))
                can_ban = bool(getattr(member, "can_restrict_members", False))
            except Exception as exc:
                logger.warning("Position huquqlari tekshirilmadi chat=%s: %s", chat_id, exc)
                await callback.answer(
                    "Bot huquqlarini tekshirib bo'lmadi.",
                    show_alert=True,
                )
                return
            if not can_delete or not can_ban:
                missing = []
                if not can_delete:
                    missing.append("xabar o'chirish")
                if not can_ban:
                    missing.append("bloklash")
                await callback.answer(
                    "Avval botga quyidagi admin huquqlarini bering: " + ", ".join(missing),
                    show_alert=True,
                )
                return
        await storage.set_state(_automatic_mode_key(chat_id), "1" if enable else "0")
        title = str(chat.get("title") or chat_id)
        result = (
            "✅ <b>To'liq avtomatik rejim yoqildi</b>\n\n"
            "Endi bot xavf darajasiga qarab xabarlarni tasdiqsiz o'chiradi va "
            "yuqori xavfli profillarni bloklaydi."
            if enable
            else "✅ <b>To'liq avtomatik rejim o'chirildi</b>\n\n"
            "Endi shubhali holatlar tasdiqlash uchun adminga yuboriladi."
        )
        if callback.message:
            await callback.message.edit_text(
                result
                + "\n\n"
                + f"Belgilangan chat: <b>{html.escape(title)}</b>\n"
                + f"Guruh ID: <code>{chat_id}</code>",
                reply_markup=None,
                parse_mode=ParseMode.HTML,
            )
        await callback.answer("Rejim yangilandi.")

    async def group_readiness_text(bot: Bot, chat_id: int) -> str:
        me = await bot.get_me()
        try:
            member = await bot.get_chat_member(chat_id, me.id)
        except Exception:
            return "⚠️ Holatimni tekshirib bo'lmadi. Meni guruhga qayta qo'shib ko'ring."
        is_admin_member = member.status in {
            ChatMemberStatus.CREATOR,
            ChatMemberStatus.ADMINISTRATOR,
        }
        if not is_admin_member:
            return (
                "⚠️ Men guruhga qo'shildim, lekin hali administrator emasman.\n"
                "Meni admin qilib, xabarlarni o'chirish va foydalanuvchilarni "
                "bloklash huquqlarini yoqing."
            )
        missing = []
        if not bool(getattr(member, "can_delete_messages", False)):
            missing.append("xabarlarni o'chirish")
        if not bool(getattr(member, "can_restrict_members", False)):
            missing.append("foydalanuvchilarni bloklash")
        if missing:
            return "⚠️ Admin huquqi yetishmayapti: " + ", ".join(missing) + "."
        return "✅ Rahmat! Endi to'liq ishga tushdim. Guruhni himoya qilaman. 👮"

    @router.my_chat_member()
    async def membership_handler(event: ChatMemberUpdated, bot: Bot) -> None:
        if event.chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP}:
            return
        admin_statuses = {
            ChatMemberStatus.CREATOR,
            ChatMemberStatus.ADMINISTRATOR,
        }
        became_admin = (
            event.new_chat_member.status in admin_statuses
            and event.old_chat_member.status not in admin_statuses
        )
        is_active = event.new_chat_member.status in {
            ChatMemberStatus.MEMBER,
            ChatMemberStatus.ADMINISTRATOR,
        }
        await storage.upsert_managed_chat(
            event.chat.id,
            event.chat.title or str(event.chat.id),
            event.chat.username or "",
            active=is_active,
        )
        if is_active:
            await bot.send_message(
                event.chat.id,
                await group_readiness_text(bot, event.chat.id),
            )
        if became_admin:
            notice = _group_admin_notice(
                event.chat.title or str(event.chat.id),
                event.chat.id,
                bool(getattr(event.new_chat_member, "can_delete_messages", False)),
                bool(getattr(event.new_chat_member, "can_restrict_members", False)),
            )
            for admin_id in settings.admin_ids:
                try:
                    await bot.send_message(admin_id, notice)
                except Exception as exc:
                    logger.warning(
                        "Yangi guruh xabari yuborilmadi admin=%s chat=%s: %s",
                        admin_id,
                        event.chat.id,
                        exc,
                    )

    @router.message(CommandStart())
    @router.message(Command("help"))
    async def start_handler(message: Message, bot: Bot) -> None:
        if message.chat.type in {ChatType.GROUP, ChatType.SUPERGROUP}:
            await message.answer(await group_readiness_text(bot, message.chat.id))
            return
        if message.chat.type != ChatType.PRIVATE:
            return
        user_text = (
            "🛡 <b>Izoh Posbon</b>\n\n"
            "Meni kanalga ulangan muhokama guruhiga administrator qilib qo'shing. "
            "Men xabar matni, bio, username, profilga biriktirilgan kanal va uning "
            "oxirgi postlarini hamda foydalanuvchi xatti-harakatini baholab, spam, "
            "scam hamda 18+ profillarni aniqlayman. AI yoqilganda profil rasmi ham "
            "tekshiriladi.\n\n"
            "👤 <b>Siz uchun</b>\n"
            "/stats — shaxsiy moderatsiya statistikangiz"
        )
        if is_panel_admin(message):
            user_text += (
                "\n\n👮 <b>Adminlar uchun</b>\n"
                "/groups — boshqariladigan guruhni tanlash\n"
                "/status — bot holati va huquqlarini tekshirish\n"
                "/recent — so'nggi aniqlangan spamlar\n"
                "/unban — ID kiritib blokni olib tashlash\n"
                "/report — Excel hisobotni yuklab olish\n"
                "/dbstats — ma'lumotlar bazasi holati\n"
                "/position — avtomatik moderatsiyani yoqish yoki o'chirish\n"
                "/del_bot — admin botning oxirgi xabarlarini o'chirish\n"
                "/leave — tanlangan guruhdan botni chiqarish"
            )
        elif is_limited_admin(message):
            user_text += (
                "\n\n👮 <b>Adminlar uchun</b>\n"
                "/status — bot holati va huquqlarini tekshirish\n"
                "/recent — so'nggi aniqlangan spamlar\n"
                "/report — Excel hisobotni yuklab olish\n"
                "/dbstats — ma'lumotlar bazasi holati"
            )
        await message.answer(user_text, parse_mode=ParseMode.HTML)

    @router.message(Command("groups"))
    async def groups_handler(message: Message) -> None:
        if not await require_private_panel_admin(message):
            return
        user = message.from_user
        if not user:
            return
        text, keyboard = await groups_panel(user.id)
        await message.answer(
            text, reply_markup=keyboard, parse_mode=ParseMode.HTML
        )

    @router.message(Command("leave"))
    async def leave_handler(message: Message) -> None:
        if not await require_private_panel_admin(message):
            return
        chat_id = await protected_chat_id_or_error(message)
        if chat_id is None:
            return
        await show_leave_confirmation(chat_id, message.answer)

    @router.message(Command("position"))
    async def position_handler(message: Message) -> None:
        if not await require_private_panel_admin(message):
            return
        chat_id = await protected_chat_id_or_error(message)
        if chat_id is None:
            return
        chat = await storage.get_managed_chat(chat_id)
        if not chat or not bool(chat.get("active")):
            await message.answer("Bu guruh faol ro'yxatda topilmadi.")
            return
        automatic_enabled = await automatic_mode_enabled(chat_id)
        await message.answer(
            _position_confirmation(
                str(chat.get("title") or chat_id),
                chat_id,
                automatic_enabled,
            ),
            reply_markup=_position_keyboard(chat_id, automatic_enabled),
            parse_mode=ParseMode.HTML,
        )

    @router.message(Command("del_bot"))
    async def del_bot_handler(message: Message, bot: Bot) -> None:
        if not await require_private_panel_admin(message):
            return
        chat_id = await protected_chat_id_or_error(message)
        if chat_id is None:
            return
        tracked_bot_ids = await storage.tracked_bot_user_ids(chat_id)
        admin_bots = []
        for bot_user_id in tracked_bot_ids:
            try:
                member = await bot.get_chat_member(chat_id, bot_user_id)
            except Exception as exc:
                logger.debug(
                    "Kuzatilgan bot holati olinmadi chat=%s bot=%s: %s",
                    chat_id,
                    bot_user_id,
                    exc,
                )
                continue
            if member.user.is_bot and member.status in {
                ChatMemberStatus.CREATOR,
                ChatMemberStatus.ADMINISTRATOR,
            }:
                admin_bots.append(member.user)
        if not admin_bots:
            await message.answer(
                "Tanlangan guruhda hali xabari kuzatilgan boshqa admin bot yo'q. "
                "Admin bot guruhga yangi xabar yuborgach /del_bot da ko'rinadi."
            )
            return
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=(item.full_name or ("@" + item.username if item.username else str(item.id)))[:50],
                        callback_data=f"delbot:select:{chat_id}:{item.id}",
                    )
                ]
                for item in admin_bots
            ]
        )
        await message.answer(
            "<b>Xabarlari o'chiriladigan admin botni tanlang</b>\n\n"
            "Telegram boshqa admin botlarni tayyor ro'yxatda bermaydi. Shu sababli "
            "Izoh Posbon kuzatgan admin botlar ko'rsatiladi va faqat kuzatilgan "
            "xabarlar o'chiriladi.",
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
        )

    @router.callback_query(F.data.startswith("delbot:select:"))
    async def del_bot_select_callback(callback: CallbackQuery, bot: Bot) -> None:
        if callback.from_user.id not in settings.admin_ids:
            await callback.answer("Bu panel faqat boshqaruvchi admin uchun.", show_alert=True)
            return
        try:
            _, _, raw_chat_id, raw_bot_id = (callback.data or "").split(":", maxsplit=3)
            chat_id = int(raw_chat_id)
            bot_user_id = int(raw_bot_id)
        except (ValueError, AttributeError):
            await callback.answer("Noto'g'ri bot tanlandi.", show_alert=True)
            return
        selected_chat_id = await storage.get_selected_chat_id(
            callback.from_user.id,
            fallback_chat_id=settings.protected_chat_id,
        )
        if selected_chat_id != chat_id:
            await callback.answer("Tanlangan guruh o'zgargan. /del_bot ni qayta bosing.", show_alert=True)
            return
        try:
            member = await bot.get_chat_member(chat_id, bot_user_id)
        except Exception:
            await callback.answer("Bot guruhda topilmadi.", show_alert=True)
            return
        if not member.user.is_bot or member.status not in {
            ChatMemberStatus.CREATOR,
            ChatMemberStatus.ADMINISTRATOR,
        }:
            await callback.answer("Tanlangan profil admin bot emas.", show_alert=True)
            return
        label = member.user.full_name or (
            "@" + member.user.username if member.user.username else str(bot_user_id)
        )
        if callback.message:
            await callback.message.edit_text(
                "<b>Nechta xabar o'chirilsin?</b>\n\n"
                f"Bot: <b>{html.escape(label)}</b>",
                reply_markup=_del_bot_count_keyboard(chat_id, bot_user_id),
                parse_mode=ParseMode.HTML,
            )
        await callback.answer("Bot tanlandi.")

    @router.callback_query(F.data.startswith("delbot:count:"))
    async def del_bot_count_callback(callback: CallbackQuery, bot: Bot) -> None:
        if callback.from_user.id not in settings.admin_ids:
            await callback.answer("Bu panel faqat boshqaruvchi admin uchun.", show_alert=True)
            return
        try:
            _, _, raw_chat_id, raw_bot_id, raw_count = (callback.data or "").split(":", maxsplit=4)
            chat_id = int(raw_chat_id)
            bot_user_id = int(raw_bot_id)
            count = int(raw_count)
        except (ValueError, AttributeError):
            await callback.answer("Noto'g'ri so'rov.", show_alert=True)
            return
        if count not in {1, 5, 10}:
            await callback.answer("Noto'g'ri xabar soni.", show_alert=True)
            return
        selected_chat_id = await storage.get_selected_chat_id(
            callback.from_user.id,
            fallback_chat_id=settings.protected_chat_id,
        )
        if selected_chat_id != chat_id:
            await callback.answer("Tanlangan guruh o'zgargan. /del_bot ni qayta bosing.", show_alert=True)
            return
        message_ids = await storage.recent_bot_message_ids(chat_id, bot_user_id, count)
        if not message_ids:
            await callback.answer("Bu botning kuzatilgan xabarlari hali yo'q.", show_alert=True)
            return
        deleted_ids = []
        for message_id in message_ids:
            try:
                await bot.delete_message(chat_id, message_id)
                deleted_ids.append(message_id)
            except Exception as exc:
                logger.warning(
                    "Admin bot xabari o'chmadi chat=%s bot=%s message=%s: %s",
                    chat_id,
                    bot_user_id,
                    message_id,
                    exc,
                )
        await storage.remove_bot_message_records(chat_id, deleted_ids)
        result = (
            "✅ <b>Muvaffaqiyatli o'chirildi</b>\n\n"
            f"O'chirilgan xabarlar: <b>{len(deleted_ids)}</b> ta"
        )
        if len(deleted_ids) < len(message_ids):
            result += f"\nO'chirib bo'lmagan xabarlar: <b>{len(message_ids) - len(deleted_ids)}</b> ta"
        if callback.message:
            await callback.message.edit_text(result, parse_mode=ParseMode.HTML)
        await callback.answer("Tozalash yakunlandi.")

    @router.message(Command("stats"))
    async def stats_handler(message: Message) -> None:
        user = message.from_user
        if not user:
            return
        if message.chat.type != ChatType.PRIVATE:
            await message.answer(
                "Shaxsiy statistikani ko'rish uchun botga private chatda /stats yuboring."
            )
            return
        stats = await storage.user_stats(user.id)
        last_event = "yo'q"
        if stats["last_event_at"]:
            last_event = datetime.fromtimestamp(stats["last_event_at"]).astimezone().strftime(
                "%Y-%m-%d %H:%M"
            )
        await message.answer(
            "👤 <b>Sizning statistikangiz</b>\n\n"
            f"Kuzatilgan matnli izohlar: <b>{stats['messages']}</b>\n"
            f"Shubhali holatlar: <b>{stats['flagged']}</b>\n"
            f"Tekshiruv qarorlari: <b>{stats['reviews']}</b>\n"
            f"O'chirish qarorlari: <b>{stats['deletions']}</b>\n"
            f"Bloklash qarorlari: <b>{stats['bans']}</b>\n"
            f"Eng yuqori risk: <b>{stats['max_score']}</b>\n"
            f"Oxirgi hodisa: <b>{last_event}</b>",
            parse_mode=ParseMode.HTML,
        )

    @router.message(Command("recent"))
    async def recent_handler(message: Message, bot: Bot) -> None:
        if not await require_private_panel_reader(message):
            return
        chat_id = await protected_chat_id_or_error(message)
        if chat_id is None:
            return
        events = await storage.recent_events(chat_id, limit=10)
        if not events:
            await message.answer("Hozircha aniqlangan spamlar yo'q.")
            return
        lines = ["🕘 <b>So'nggi aniqlangan spamlar</b>"]
        for index, event in enumerate(events, start=1):
            event_time = datetime.fromtimestamp(event["created_at"]).astimezone().strftime(
                "%m-%d %H:%M"
            )
            display_name = event.get("full_name") or event.get("username") or str(event["user_id"])
            lines.append(
                f"\n{index}. <b>{html.escape(display_name)}</b> "
                f"(<code>{event['user_id']}</code>)\n"
                f"{event_time} · risk <b>{event['score']}</b> · "
                f"{html.escape(str(event['action']))}\n"
                f"{html.escape((event.get('message_text') or '[media]')[:160])}"
            )
        await message.answer("\n".join(lines), parse_mode=ParseMode.HTML)

    async def apply_unban(
        message: Message,
        bot: Bot,
        chat_id: int,
        user_id: int,
    ) -> None:
        try:
            await bot.unban_chat_member(chat_id, user_id, only_if_banned=True)
        except Exception as exc:
            logger.warning("Unban xatosi chat=%s user=%s: %s", chat_id, user_id, exc)
            await message.answer("Blokni olib tashlab bo'lmadi. Bot huquqlarini tekshiring.")
            return
        await storage.mark_unblocked_user(chat_id, user_id, message.from_user.id)
        await storage.clear_emoji_violations(chat_id, user_id)
        await storage.clear_link_violations(chat_id, user_id)
        await message.answer(
            f"✅ <a href=\"tg://user?id={user_id}\">Foydalanuvchi</a> blokdan chiqarildi.",
            parse_mode=ParseMode.HTML,
        )

    @router.message(Command("unban"))
    async def unban_handler(message: Message, bot: Bot, state: FSMContext) -> None:
        if not await require_private_panel_admin(message):
            return
        chat_id = await protected_chat_id_or_error(message)
        if chat_id is None:
            return
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) == 1:
            await state.set_state(UnbanFlow.waiting_for_user_id)
            await state.update_data(chat_id=chat_id)
            await message.answer("Foydalanuvchi ID raqamini kiriting.")
            return
        user_id = _parse_positive_user_id(parts[1])
        if user_id is None:
            await message.answer("User ID musbat raqam bo'lishi kerak.")
            return
        await state.clear()
        await apply_unban(message, bot, chat_id, user_id)

    @router.message(
        UnbanFlow.waiting_for_user_id,
        F.text,
        ~F.text.startswith("/"),
    )
    async def unban_user_id_handler(
        message: Message,
        bot: Bot,
        state: FSMContext,
    ) -> None:
        if not await require_private_panel_admin(message):
            await state.clear()
            return
        user_id = _parse_positive_user_id(message.text or "")
        if user_id is None:
            await message.answer(
                "User ID faqat musbat raqamlardan iborat bo'lishi kerak. "
                "Qayta yuboring."
            )
            return
        data = await state.get_data()
        chat_id = data.get("chat_id")
        await state.clear()
        if not isinstance(chat_id, int):
            await message.answer("Guruh aniqlanmadi. /unban buyrug'ini qayta bosing.")
            return
        await apply_unban(message, bot, chat_id, user_id)

    @router.message(Command("dbstats"))
    async def database_stats_handler(message: Message) -> None:
        if not await require_private_panel_reader(message):
            return
        stats = await storage.database_stats(
            settings.limited_admin_chat_id if is_limited_admin(message) else None
        )
        await message.answer(
            "<b>Ma'lumotlar bazasi</b>\n\n"
            f"Moderatsiya hodisalari: <b>{stats['moderation_events']}</b>\n"
            f"Kutilayotgan qarorlar: <b>{stats['pending_actions']}</b>\n"
            f"Bloklash tarixi: <b>{stats['blocked_users']}</b>\n"
            f"Profil tekshiruvlari: <b>{stats['profile_checks']}</b>\n"
            f"AI tekshiruvlari: <b>{stats['ai_usage']}</b>\n"
            f"Emoji/sticker qoidabuzarliklari: <b>{stats['emoji_violations']}</b>\n"
            f"Havolali xabar qoidabuzarliklari: <b>{stats['link_violations']}</b>\n"
            f"Kuzatilgan bot xabarlari: <b>{stats['bot_messages']}</b>\n"
            f"Guruhlar: <b>{stats['managed_chats']}</b>"
        )

    @router.message(Command("report"))
    async def report_handler(message: Message, bot: Bot) -> None:
        if not await require_private_panel_reader(message):
            return
        chat_id = await protected_chat_id_or_error(message)
        if chat_id is None:
            return
        events = await storage.report_events(chat_id)
        if not events:
            await message.answer("Hisobot uchun hali moderatsiya hodisalari yo'q.")
            return
        now = datetime.now().astimezone()
        try:
            protected_chat = await bot.get_chat(chat_id)
            protected_title = protected_chat.title or str(chat_id)
        except Exception:
            protected_title = str(chat_id)
        report_bytes = build_excel_report(
            events,
            protected_title,
            now.replace(tzinfo=None),
        )
        filename = "izoh_posbon_" + now.strftime("%Y%m%d_%H%M") + ".xlsx"
        await message.answer_document(
            BufferedInputFile(report_bytes, filename=filename),
            caption=f"📊 {len(events)} ta moderatsiya hodisasi bo'yicha Excel hisobot.",
        )

    @router.message(Command("status"))
    async def status_handler(message: Message, bot: Bot) -> None:
        if not (is_panel_admin(message) or is_limited_admin(message)):
            await message.answer("Bu buyruq faqat ruxsat etilgan admin uchun.")
            return
        if is_limited_admin(message) and message.chat.type != ChatType.PRIVATE:
            await message.answer("Bu buyruq faqat bot bilan private chatda ishlaydi.")
            return
        if message.chat.type == ChatType.PRIVATE:
            chat_id = await protected_chat_id_or_error(message)
            if chat_id is None:
                return
        elif message.chat.type in {ChatType.GROUP, ChatType.SUPERGROUP}:
            chat_id = message.chat.id
            await storage.upsert_managed_chat(
                message.chat.id,
                message.chat.title or str(message.chat.id),
                message.chat.username or "",
                active=True,
            )
        else:
            await message.answer("Bu buyruq bu turdagi chatda ishlamaydi.")
            return

        me = await bot.get_me()
        member = await bot.get_chat_member(chat_id, me.id)
        can_delete = bool(getattr(member, "can_delete_messages", False))
        can_ban = bool(getattr(member, "can_restrict_members", False))
        delete_state = "bor" if can_delete else "yo'q"
        ban_state = "bor" if can_ban else "yo'q"
        automatic_enabled = await automatic_mode_enabled(chat_id)
        await message.answer(
            "<b>Izoh Posbon holati</b>\n"
            f"Rejim: <b>{'TO‘LIQ AVTOMATIK' if automatic_enabled else 'TASDIQLI SINOV'}</b>\n"
            f"Xabar o'chirish huquqi: <b>{delete_state}</b>\n"
            f"Bloklash huquqi: <b>{ban_state}</b>\n"
            f"Guruh ID: <code>{chat_id}</code>\n"
            f"Chegaralar: {settings.review_threshold}/{settings.delete_threshold}/{settings.ban_threshold}",
            parse_mode=ParseMode.HTML,
        )

    async def moderate_message(message: Message, bot: Bot) -> None:
        if message.chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP}:
            return
        user = message.from_user
        if not user or user.is_bot or message.sender_chat:
            return
        if await is_admin(bot, message.chat.id, user, allow_on_error=True):
            return

        text = (message.text or message.caption or "").strip()
        dangerous_files = _dangerous_attachment_names(message)
        dangerous_link = contains_dangerous_file_link(text)
        if dangerous_files or dangerous_link:
            details = []
            if dangerous_files:
                details.append("fayl: " + ", ".join(dangerous_files[:3]))
            if dangerous_link:
                details.append("taqiqlangan fayl havolasi")
            decision = ModerationDecision(
                score=100,
                action=ModerationAction.BAN,
                signals=[
                    Signal(
                        "dangerous_file",
                        100,
                        "Qat'iy taqiqlangan fayl yoki havola — " + "; ".join(details),
                    )
                ],
            )
            action_result = await _apply_action(
                bot,
                message,
                user,
                decision,
                settings,
                storage,
                force=True,
            )
            audit_text = text or ", ".join(dangerous_files) or "[taqiqlangan fayl]"
            audit_results = await asyncio.gather(
                storage.record_message(message.chat.id, user.id, audit_text),
                storage.record_event(
                    message.chat.id,
                    user.id,
                    message.message_id,
                    audit_text,
                    decision,
                    full_name=user.full_name,
                    username=user.username or "",
                    chat_title=message.chat.title or "",
                ),
                return_exceptions=True,
            )
            for audit_error in audit_results:
                if isinstance(audit_error, Exception):
                    logger.warning("Fayl moderatsiya auditi yozilmadi: %s", audit_error)
            await _send_log(bot, message, user, decision, settings, action_result)
            return

        if _message_has_link_or_username(message):
            violation_message_count = await storage.record_link_violation(
                message.chat.id,
                user.id,
            )
            decision = _link_violation_decision(violation_message_count)
            action_result = await _apply_action(
                bot,
                message,
                user,
                decision,
                settings,
                storage,
                force=True,
            )
            audit_results = await asyncio.gather(
                storage.record_message(message.chat.id, user.id, text),
                storage.record_event(
                    message.chat.id,
                    user.id,
                    message.message_id,
                    text or "[yashirin havola]",
                    decision,
                    full_name=user.full_name,
                    username=user.username or "",
                    chat_title=message.chat.title or "",
                ),
                return_exceptions=True,
            )
            for audit_error in audit_results:
                if isinstance(audit_error, Exception):
                    logger.warning("Havola moderatsiya auditi yozilmadi: %s", audit_error)
            await _send_log(bot, message, user, decision, settings, action_result)
            return

        sticker_emoji = (
            (getattr(message.sticker, "emoji", None) or "")
            if message.sticker
            else ""
        )
        emoji_payload = "\n".join(part for part in (text, sticker_emoji) if part)
        emoji_count = prohibited_emoji_count(emoji_payload)
        if emoji_count:
            violation_message_count = await storage.record_emoji_violation(
                message.chat.id,
                user.id,
            )
            decision = _emoji_violation_decision(
                emoji_count,
                violation_message_count,
            )
            action_result = await _apply_action(
                bot,
                message,
                user,
                decision,
                settings,
                storage,
                force=True,
            )
            audit_results = await asyncio.gather(
                storage.record_message(
                    message.chat.id,
                    user.id,
                    text or sticker_emoji or "[sticker]",
                ),
                storage.record_event(
                    message.chat.id,
                    user.id,
                    message.message_id,
                    text or sticker_emoji or "[sticker]",
                    decision,
                    full_name=user.full_name,
                    username=user.username or "",
                    chat_title=message.chat.title or "",
                ),
                return_exceptions=True,
            )
            for audit_error in audit_results:
                if isinstance(audit_error, Exception):
                    logger.warning("Emoji moderatsiya auditi yozilmadi: %s", audit_error)
            await _send_log(bot, message, user, decision, settings, action_result)
            return

        profile_task = asyncio.create_task(profile_loader.load(bot, user))
        duplicate_count, coordinated_user_count = await asyncio.gather(
            storage.duplicate_count(user.id, text, message.chat.id),
            storage.coordinated_user_count(
                message.chat.id,
                user.id,
                text,
                settings.coordinated_window_seconds,
            ),
        )
        if coordinated_user_count < settings.coordinated_min_users:
            coordinated_user_count = 0
        seconds_after_post = _seconds_after_channel_post(message)
        quick_profile = ProfileSnapshot(
            user_id=user.id,
            full_name=user.full_name,
            username=user.username or "",
        )
        quick_context = ModerationContext(
            text=text,
            profile=quick_profile,
            chat_id=message.chat.id,
            duplicate_count=duplicate_count,
            coordinated_user_count=coordinated_user_count,
            seconds_after_post=seconds_after_post,
        )
        quick_decision = engine.evaluate_local(quick_context)
        if quick_decision.action in {
            ModerationAction.DELETE,
            ModerationAction.BAN,
        }:
            # Aniq so'kish/spam topilganda sekin profil va AI javobini kutmaymiz.
            profile_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await profile_task
            profile = quick_profile
            decision = quick_decision
        else:
            profile = await profile_task
            context = ModerationContext(
                text=text,
                profile=profile,
                chat_id=message.chat.id,
                duplicate_count=duplicate_count,
                coordinated_user_count=coordinated_user_count,
                seconds_after_post=seconds_after_post,
            )
            decision = await engine.evaluate(context)
        await storage.record_message(message.chat.id, user.id, text)
        await storage.record_profile_check(
            message.chat.id,
            user.id,
            user.full_name,
            user.username or "",
            profile.bio,
            len(profile.photo_samples) or (1 if profile.photo_bytes else 0),
            decision,
        )
        if decision.ai_categories:
            await storage.record_ai_usage(
                message.chat.id,
                user.id,
                "openai",
                "omni-moderation-latest",
                decision.ai_categories,
            )

        if decision.action == ModerationAction.ALLOW:
            return

        await storage.record_event(
            message.chat.id,
            user.id,
            message.message_id,
            text,
            decision,
            full_name=user.full_name,
            username=user.username or "",
            chat_title=message.chat.title or "",
        )
        automatic_enabled = await automatic_mode_enabled(message.chat.id)
        if not automatic_enabled:
            action_id = await storage.create_pending_action(
                chat_id=message.chat.id,
                chat_title=message.chat.title or "",
                user_id=user.id,
                message_id=message.message_id,
                full_name=user.full_name,
                username=user.username or "",
                message_text=text,
                decision=decision,
            )
            await send_approval_request(bot, action_id)
            logger.warning(
                "ADMIN_APPROVAL_PENDING action=%s chat=%s user=%s score=%s",
                action_id,
                message.chat.id,
                user.id,
                decision.score,
            )
            return
        action_result = await _apply_action(
            bot,
            message,
            user,
            decision,
            settings,
            storage,
            force=True,
        )
        await _send_log(bot, message, user, decision, settings, action_result)

    async def delete_membership_service_message(message: Message, bot: Bot) -> None:
        """Guruhga qo'shilish va guruhdan chiqish xizmat xabarlarini tozalaydi."""
        if message.chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP}:
            return
        if not _is_membership_service_message(message):
            return
        try:
            await bot.delete_message(message.chat.id, message.message_id)
        except Exception as exc:
            logger.warning(
                "A'zo qo'shilgani/chiqqani haqidagi xizmat xabari o'chmadi "
                "chat=%s message=%s: %s",
                message.chat.id,
                message.message_id,
                exc,
            )

    # Spamchi avval oddiy matn yozib, keyin 18+ havolaga tahrirlashi mumkin.
    # Shu sababli yangi va tahrirlangan xabarlar bir xil tekshiriladi.
    async def track_bot_message(message: Message, bot: Bot) -> None:
        if message.chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP}:
            return
        user = message.from_user
        if not user or not user.is_bot or user.id == bot.id:
            return
        await storage.record_bot_message(message.chat.id, user.id, message.message_id)

    # Bot foydalanuvchini chiqarganida xizmat xabarining muallifi botning o'zi
    # bo'ladi. Shu sabab bu handler boshqa botlar xabarini kuzatuvchidan oldin
    # turishi shart; aks holda aiogram yangilanishni track_bot_message'da
    # to'xtatib, xizmat xabarini o'chirishga yetkazmaydi.
    router.message.register(
        delete_membership_service_message,
        F.new_chat_members | F.left_chat_member,
    )
    router.message.register(track_bot_message, F.from_user.is_bot)
    router.message.register(moderate_message)
    router.edited_message.register(moderate_message)

    return router


def _seconds_after_channel_post(message: Message) -> Optional[int]:
    replied = message.reply_to_message
    if not replied or not getattr(replied, "is_automatic_forward", False):
        return None
    delta = message.date - replied.date
    return max(0, int(delta.total_seconds()))


async def _apply_action(
    bot: Bot,
    message: Message,
    user: User,
    decision: ModerationDecision,
    settings: Settings,
    storage: Optional[Storage] = None,
    force: bool = False,
) -> str:
    if settings.dry_run and not force:
        return "SINOV: hech narsa o'zgartirilmadi"
    if decision.action == ModerationAction.REVIEW:
        return "Faqat tekshiruvga yuborildi"

    results = []
    try:
        await bot.delete_message(message.chat.id, message.message_id)
        results.append("izoh o'chirildi")
    except Exception as exc:
        logger.exception("Xabarni o'chirish xatosi")
        results.append("o'chirishda xato: " + str(exc))

    if decision.action == ModerationAction.BAN:
        try:
            await bot.ban_chat_member(
                message.chat.id,
                user.id,
                revoke_messages=True,
            )
            results.append("user bloklandi")
            if storage:
                try:
                    await storage.record_blocked_user(
                        message.chat.id,
                        user.id,
                        user.full_name,
                        user.username or "",
                        "; ".join(signal.detail for signal in decision.signals),
                    )
                except Exception as exc:
                    logger.warning(
                        "Avtomatik bloklash auditi yozilmadi chat=%s user=%s: %s",
                        message.chat.id,
                        user.id,
                        exc,
                    )
        except Exception as exc:
            logger.exception("Userni bloklash xatosi")
            results.append("bloklashda xato: " + str(exc))
    return "; ".join(results)


async def _send_log(
    bot: Bot,
    message: Message,
    user: User,
    decision: ModerationDecision,
    settings: Settings,
    action_result: str,
) -> None:
    reasons = "\n".join(
        f"• +{signal.points}: {html.escape(signal.detail)}"
        for signal in decision.signals
    ) or "• Signal yo'q"
    username = "@" + user.username if user.username else "username yo'q"
    sticker_emoji = (
        (getattr(message.sticker, "emoji", None) or "")
        if getattr(message, "sticker", None)
        else ""
    )
    attachment_names = _dangerous_attachment_names(message)
    content = (
        message.text
        or message.caption
        or (f"[fayl: {', '.join(attachment_names)}]" if attachment_names else "")
        or (f"[sticker: {sticker_emoji}]" if sticker_emoji else "[media/xizmatsiz xabar]")
    )[:500]
    log_text = (
        f"🛡 <b>Moderatsiya: {decision.action.value.upper()}</b>\n"
        f"Risk: <b>{decision.score}</b>\n"
        f"User: <a href=\"tg://user?id={user.id}\">{html.escape(user.full_name)}</a> "
        f"({html.escape(username)}, <code>{user.id}</code>)\n"
        f"Guruh: {html.escape(message.chat.title or str(message.chat.id))}\n"
        f"Natija: {html.escape(action_result)}\n\n"
        f"<b>Sabablar</b>\n{reasons}\n\n"
        f"<b>Xabar</b>\n{html.escape(content)}"
    )

    targets = set(settings.admin_ids)
    if settings.mod_log_chat_id:
        targets.add(settings.mod_log_chat_id)
    if targets:
        target_ids = sorted(targets)
        deliveries = await asyncio.gather(
            *(
                bot.send_message(
                    target_id,
                    log_text,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                )
                for target_id in target_ids
            ),
            return_exceptions=True,
        )
        for target_id, delivery in zip(target_ids, deliveries):
            if isinstance(delivery, Exception):
                logger.warning(
                    "Moderatsiya natijasi yuborilmadi target=%s: %s",
                    target_id,
                    delivery,
                )
    logger.warning(
        "MODERATION chat=%s user=%s score=%s action=%s reasons=%s",
        message.chat.id,
        user.id,
        decision.score,
        decision.action.value,
        [signal.code for signal in decision.signals],
    )
