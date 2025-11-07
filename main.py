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

CONVERSATION_CANCEL_KEYBOARD = [["❌ Cancel"]]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user

    await update.message.reply_html(
        f"Hello, {user.mention_html()}! Use the button below to start submitting a review.",
        reply_markup=ReplyKeyboardMarkup(
            MAIN_MENU_KEYBOARD,
            one_time_keyboard=True,
            resize_keyboard=True,
            input_field_placeholder="Select an option"
        ),
    )
    return ConversationHandler.END

async def start_review_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Пишите только контакты на того кого оставляете отклик, например название фирмы, ник в Телеграме, email. Другие пользователи группы обратяться к вам за отзывом, при необходимости.",
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

    user_name = user.full_name
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
            f"❌ An error occurred while sending the notification. Please check the bot's configuration and permissions in the admin group. Error: {e}",
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
        "🛑 **REVIEW DELETION REQUEST** 🛑\n\n"
        f"**User:** {user.mention_html()} (ID: `{user.id}`)\n"
        "This user is requesting that **ALL** of their previously submitted reviews "
        "and related records be permanently deleted from the database/logs.\n\n"
        "**ACTION REQUIRED BY ADMIN**"
    )

    try:
        if not chat_id:
             await context.bot.send_message(
                chat_id=user.id,
                text="⚠️ Warning: Admin chat ID is not configured. Deletion request was only logged."
            )
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text=retraction_message,
                parse_mode='HTML'
            )

    except Exception as e:
        await update.message.reply_text(
            f"❌ An error occurred while sending the deletion request. Please contact support manually. Error: {e}",
            reply_markup=ReplyKeyboardMarkup(MAIN_MENU_KEYBOARD, one_time_keyboard=True),
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "✅ Your request to remove all your submitted reviews has been forwarded to the administration. "
        "An admin will manually process this request.",
        reply_markup=ReplyKeyboardMarkup(MAIN_MENU_KEYBOARD, one_time_keyboard=True),
    )
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Conversation cancelled. What would you like to do next?",
        reply_markup=ReplyKeyboardMarkup(MAIN_MENU_KEYBOARD, one_time_keyboard=True),
    )
    return ConversationHandler.END

async def fallback_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "I'm not sure what you mean. Use the 'Write a review' button or /start.",
        reply_markup=ReplyKeyboardMarkup(MAIN_MENU_KEYBOARD, one_time_keyboard=True),
    )

def main():
    application = Application.builder().token(bot_api_key).build()

    review_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^✍️ Написать отклик$"), start_review_conversation),
        ],

        states={
            ASK_CONTACTS: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^❌ Cancel$"), get_contacts_and_notify)],
        },

        fallbacks=[
            MessageHandler(filters.Regex("^❌ Cancel$"), cancel),
            CommandHandler("cancel", cancel)
        ],
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex("^[Ss]tart$"), start))
    application.add_handler(review_handler)

    application.add_handler(MessageHandler(filters.Regex("^🗑️ Удалить все отклики$"), remove_reviews))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, fallback_text))

    print("Bot is running. Press Ctrl-C to stop.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
