from telegram import Update
from telegram.ext import ContextTypes
from keyboards.main_menu import main_menu
from services.user_service import has_registered_account

async def start(update:Update, context: ContextTypes.DEFAULT_TYPE):
    # update = response from user
    user = getattr(update, "effective_user", None);
    user_id = getattr(user, "id", None)

    if user_id is not None and not has_registered_account(user_id):
        await update.message.reply_text(
            "Welcome to daizoubu. Please register first.\n"
            "Send: Register <username> <SUTD_ID>\n"
            "Example: Register himeko 1001234"
        )
        return

    display_name = getattr(user, "first_name", "there")
    await update.message.reply_text("Welcome to daizoubu, " + display_name + "!",
    reply_markup = main_menu(user));