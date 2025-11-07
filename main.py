import os
import csv
import logging
from typing import Final, Dict, Any, Tuple
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
    ConversationHandler,
    CallbackQueryHandler,
)
from dotenv import load_dotenv
import time

load_dotenv()

bot_api_key = os.environ["TELEGRAM_BOT_API_KEY"]
chat_id = os.environ["TELEGRAM_CHAT_ID"]

try:
    ADMIN_ID = int(os.environ.get("TELEGRAM_ADMIN_ID", 0))
    if ADMIN_ID == 0:
        logging.warning("TELEGRAM_ADMIN_ID не установлен. Процесс одобрения не будет работать.")
except ValueError:
    logging.error("TELEGRAM_ADMIN_ID должен быть целым числом (User ID).")
    ADMIN_ID = 0


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

ASK_CONTACTS = 0

MAIN_MENU_KEYBOARD = [
    ["✍️ Написать отклик"],
    ["🗑️ Удалить все отклики"]
]

CONVERSATION_CANCEL_KEYBOARD = [["❌ Отмена"]]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user

    await update.message.reply_html(
        f"Привет, {user.mention_html()}! Используйте кнопку ниже, чтобы начать оставлять отзыв.",
        reply_markup=ReplyKeyboardMarkup(
            MAIN_MENU_KEYBOARD,
            one_time_keyboard=True,
            resize_keyboard=True,
            input_field_placeholder="Выберите опцию"
        ),
    )
    return ConversationHandler.END

async def start_review_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Укажите только контакты того, о ком вы оставляете отклик (например, название компании, ник в Телеграме, email). Другие пользователи группы смогут обратиться к вам за отзывом, при необходимости.",
        reply_markup=ReplyKeyboardMarkup(
            CONVERSATION_CANCEL_KEYBOARD,
            one_time_keyboard=True,
            resize_keyboard=True
        ),
        parse_mode='Markdown'
    )
    return ASK_CONTACTS

async def get_contacts_and_notify(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    website_contacts = update.message.text
    user = update.effective_user

    user_display = f"@{user.username}" if user.username else str(user.id)
    original_user_id = user.id

    context.bot_data[f"pending_review_{original_user_id}"] = website_contacts

    approval_message = (
        f"**НОВЫЙ ОТКЛИК НА ПРОВЕРКЕ**\n\n"
        f"**Автор:** {user_display} (ID: `{original_user_id}`)\n"
        f"**Контакт:** {website_contacts}\n\n"
        f"Одобрить и отправить в канал {chat_id}?"
    )

    keyboard = [
        [
            InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_{original_user_id}"),
            InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{original_user_id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        if ADMIN_ID == 0:
             await update.message.reply_text(
                 "❌ Администратор не настроен (`TELEGRAM_ADMIN_ID`). Не могу отправить на проверку. Публикация отменена.",
                 reply_markup=ReplyKeyboardMarkup(MAIN_MENU_KEYBOARD, one_time_keyboard=True),
             )
             return ConversationHandler.END

        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=approval_message,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

        await update.message.reply_text(
            "✅ Ваш отклик получен и отправлен администратору на проверку. Вы получите уведомление о публикации или отклонении.",
            reply_markup=ReplyKeyboardMarkup(MAIN_MENU_KEYBOARD, one_time_keyboard=True),
        )

    except Exception as e:
        logger.error(f"Error sending approval request to admin {ADMIN_ID}: {e}")
        await update.message.reply_text(
            f"❌ Произошла ошибка при отправке запроса администратору. Пожалуйста, проверьте конфигурацию бота и `TELEGRAM_ADMIN_ID`. Ошибка: {e}",
            reply_markup=ReplyKeyboardMarkup(MAIN_MENU_KEYBOARD, one_time_keyboard=True),
        )
        if f"pending_review_{original_user_id}" in context.bot_data:
             del context.bot_data[f"pending_review_{original_user_id}"]
        return ConversationHandler.END

    return ConversationHandler.END

async def handle_review_approval(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    admin_user = query.from_user

    if admin_user.id != ADMIN_ID:
        await query.edit_message_text("❌ У вас нет прав для выполнения этого действия.")
        return

    try:
        data = query.data.split('_')
        action = data[0]
        original_user_id = int(data[1])

        data_key = f"pending_review_{original_user_id}"

        website_contacts_full = context.bot_data.pop(data_key, None)

        if not website_contacts_full:
             logger.warning(f"Full review data not found for user ID {original_user_id}. Action: {action}")
             await query.edit_message_text(f"❌ Не удалось найти полный текст отзыва для пользователя ID {original_user_id}. Возможно, бот был перезапущен или действие уже было выполнено.")
             return

        original_author_id_for_admin_msg = f"ID: {original_user_id}"

        if action == 'approve':
            user_link = str(original_user_id)

            try:
                user_chat = await context.bot.get_chat(original_user_id)
                if user_chat.username:
                    user_link = f"@{user_chat.username}"
                else:
                    user_link = user_chat.mention_markdown()

            except Exception as e:
                logger.warning(f"Could not fetch user details for {original_user_id}: {e}. Falling back to ID.")

            notification_message = (
                f"Новый отзыв. Пользователь {user_link} может поделиться опытом работы с **{website_contacts_full}**"
            )

            await context.bot.send_message(
                chat_id=chat_id,
                text=notification_message,
                parse_mode='Markdown'
            )

            await context.bot.send_message(
                chat_id=original_user_id,
                text=f"✅ Ваш отклик о контакте **{website_contacts_full}** был **одобрен** и опубликован в канале!",
                parse_mode='Markdown'
            )

            await query.edit_message_text(
                f"✅ **ОДОБРЕНО И ОПУБЛИКОВАНО**\n\nКонтакт: {website_contacts_full}\nАвтор: {user_link}\nАдминистратор: {admin_user.mention_html()}",
                parse_mode='HTML'
            )

        elif action == 'reject':
            await context.bot.send_message(
                chat_id=original_user_id,
                text=f"❌ Ваш отклик о контакте **{website_contacts_full}** был **отклонен** администратором.",
                parse_mode='Markdown'
            )

            await query.edit_message_text(
                f"❌ **ОТКЛОНЕНО**\n\nКонтакт: {website_contacts_full}\nАвтор ID: {original_author_id_for_admin_msg}\nАдминистратор: {admin_user.mention_html()}",
                parse_mode='HTML'
            )

    except Exception as e:
        logger.error(f"Error in handle_review_approval: {e}")
        try:
             await query.edit_message_text(f"❌ Произошла внутренняя ошибка при обработке запроса: {e}")
        except:
             logger.error("Could not inform admin about the internal error.")


async def remove_reviews(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user

    retraction_message = (
        "🛑 **ЗАПРОС НА УДАЛЕНИЕ ОТЗЫВОВ** 🛑\n\n"
        f"**Пользователь:** {user.mention_html()} (ID: `{user.id}`)\n"
        "Этот пользователь запрашивает **ПОЛНОЕ** удаление всех ранее оставленных им отзывов "
        "и связанных записей из базы данных/логов.\n\n"
        "**ТРЕБУЕТСЯ ДЕЙСТВИЕ АДМИНИСТРАТОРА**"
    )

    try:
        if ADMIN_ID == 0:
             await context.bot.send_message(
                 chat_id=user.id,
                 text="⚠️ Внимание: ID администратора не настроен. Запрос на удаление был только зарегистрирован в логах."
             )
        else:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=retraction_message,
                parse_mode='HTML'
            )

    except Exception as e:
        await update.message.reply_text(
            f"❌ Произошла ошибка при отправке запроса на удаление. Пожалуйста, свяжитесь со службой поддержки вручную. Ошибка: {e}",
            reply_markup=ReplyKeyboardMarkup(MAIN_MENU_KEYBOARD, one_time_keyboard=True),
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "✅ Ваш запрос на удаление всех ваших отзывов был передан администрации. "
        "Администратор обработает этот запрос вручную.",
        reply_markup=ReplyKeyboardMarkup(MAIN_MENU_KEYBOARD, one_time_keyboard=True),
    )
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.effective_user.id and f"pending_review_{update.effective_user.id}" in context.bot_data:
        del context.bot_data[f"pending_review_{update.effective_user.id}"]

    await update.message.reply_text(
        "Разговор отменен. Что бы вы хотели сделать дальше?",
        reply_markup=ReplyKeyboardMarkup(MAIN_MENU_KEYBOARD, one_time_keyboard=True),
    )
    return ConversationHandler.END

async def fallback_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Я не понимаю, что вы имеете в виду. Используйте кнопку '✍️ Написать отклик' или команду /start.",
        reply_markup=ReplyKeyboardMarkup(MAIN_MENU_KEYBOARD, one_time_keyboard=True),
    )

def main():
    application = Application.builder().token(bot_api_key).build()

    review_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^✍️ Написать отклик$"), start_review_conversation),
        ],

        states={
            ASK_CONTACTS: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^❌ Отмена$"), get_contacts_and_notify)],
        },

        fallbacks=[
            MessageHandler(filters.Regex("^❌ Отмена$"), cancel),
            CommandHandler("cancel", cancel)
        ],
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex("^[Ss]tart$"), start))
    application.add_handler(review_handler)

    application.add_handler(CallbackQueryHandler(handle_review_approval, pattern="^(approve|reject)_"))

    application.add_handler(MessageHandler(filters.Regex("^🗑️ Удалить все отклики$"), remove_reviews))

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, fallback_text))

    print("Бот запущен. Нажмите Ctrl-C для остановки.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
