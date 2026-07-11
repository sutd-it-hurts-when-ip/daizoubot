from telegram import Update
from telegram.ext import ContextTypes
from keyboards.main_menu import main_menu

async def start(update:Update, context: ContextTypes.DEFAULT_TYPE):
    # update = response from user
    user = update.effective_user;
    await update.message.reply_text("Welcome to daizoubu, " + user.first_name + "!",
    reply_markup = main_menu(user));