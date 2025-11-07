import os
import csv
import logging
from typing import Final, Dict, Any, Tuple
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
    ConversationHandler,
)
from dotenv import load_dotenv

load_dotenv()

# Variables are kept as non-localized environment variables
bot_api_key = os.environ["TELEGRAM_BOT_API_KEY"]
chat_id = os.environ["TELEGRAM_CHAT_ID"]

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

    user_mention = user.mention_html()

    notification_message = (
        f"Новый отзыв. Пользователь {user_mention} может поделиться опытом работы с {website_contacts}"
    )

    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=notification_message,
            parse_mode='HTML'
        )

    except Exception as e:
        await update.message.reply_text(
            f"❌ Произошла ошибка при отправке уведомления. Пожалуйста, проверьте конфигурацию бота и его права в группе администраторов. Ошибка: {e}",
            reply_markup=ReplyKeyboardMarkup(MAIN_MENU_KEYBOARD, one_time_keyboard=True),
        )
        return ConversationHandler.END


    await update.message.reply_text(
        "✅ Отклик отправлен в XBoard @KRMN @reviewsxboard",
        reply_markup=ReplyKeyboardMarkup(MAIN_MENU_KEYBOARD, one_time_keyboard=True),
    )

    return ConversationHandler.END

async def remove_reviews(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user

    retraction_message = (
        f"Пользователь: {user.mention_html()} запрашивает удаление всех отзывов"
    )

    try:
        if not chat_id:
             await context.bot.send_message(
                chat_id=user.id,
                text="⚠️ Внимание: ID чата администратора не настроен. Запрос на удаление был только зарегистрирован в логах."
            )
        else:
            await context.bot.send_message(
                chat_id=chat_id,
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

    application.add_handler(MessageHandler(filters.Regex("^🗑️ Удалить все отклики$"), remove_reviews))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, fallback_text))

    print("Бот запущен. Нажмите Ctrl-C для остановки.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
