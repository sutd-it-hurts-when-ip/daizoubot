from telegram import Update
from telegram.ext import ContextTypes
from handlers.menu import browse_menu, view_orders, view_bounties, view_accepted_bounties
from keyboards.main_menu import main_menu
from services.user_service import create_user_account, has_registered_account, is_valid_student_id

# parse register command
# just like discord bots
def _parse_register_payload(text, user):
    parts = text.strip().split()
    if len(parts) < 2 or parts[0].lower() != "register":
        return None, None

    # Register <username> <student_id>
    if len(parts) >= 3:
        return parts[1], parts[2]

    # Register <student_id> (username falls back to Telegram username/first_name)
    fallback_username = None
    if user:
        fallback_username = user.username or user.first_name or f"user_{user.id}"
    return fallback_username, parts[1]

async def router(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = update.message.text;
    user = getattr(update, "effective_user", None)
    user_id = getattr(user, "id", None)

    # first listener : before registered check
    if text and text.lower().startswith("register"):
        username, student_id = _parse_register_payload(text, user)
        if not username or not is_valid_student_id(student_id):
            await update.message.reply_text(
                "Invalid registration format or SUTD ID.\n"
                "Send: Register <username> <SUTD_ID>\n"
                "Example: Register himeko 1001234"
            )
            return

        # returns None if something went wrong (DB down, invalid args, etc)
        # will just return profile if already exists
        created = create_user_account(user_id, username, student_id)
        if not created:
            await update.message.reply_text(
                "Registration failed. Please try again."
            )
            return

        # if we reach here, registration successful (or already registered)
        await update.message.reply_text(
            "Registration successful. Welcome to daizoubu, " + str(created.get("username")) + "!",
            reply_markup=main_menu(user),
        )
        return

    # If user not registered, prompt registration and do not listen to the other commands below (return)
    # gate for profile completion, not authentication. Users are implicitly authenticated by Telegram (thanks Tele)
    if user_id is not None and not has_registered_account(user_id):
        await update.message.reply_text(
            "Please register first.\n"
            "Send: Register <username> <SUTD_ID>\n"
            "Example: Register acane 1001234"
        )
        return

    if text == "Browse Menu": await browse_menu(update, context)
    elif text == "Available Bounties": await view_bounties(update, context)
    elif text == "My Orders": await view_orders(update, context)
    elif text == "Accepted Bounties": await view_accepted_bounties(update, context)

    else:
        await update.message.reply_text(
            "Unknown command"
        );