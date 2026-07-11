from telegram import Update
from telegram.ext import ContextTypes
from handlers.menu import browse_menu

async def router(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = update.message.text

    if text == "Browse Menu":
        await browse_menu(update, context)
    elif text == "Available Bounties":
        await update.message.reply_text("Available Bounties coming soon.")
    elif text == "My Orders":
        await update.message.reply_text("Orders coming soon.")
    elif text == "My Profile":
        await update.message.reply_text("Profile coming soon.")

    else:
        await update.message.reply_text(
            "Unknown command"
        )