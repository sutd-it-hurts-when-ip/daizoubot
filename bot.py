from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from config import BOT_TOKEN
from handlers.start import start
from handlers.menu import browse_menu, vendor_selected, food_selected, add_to_cart, view_cart, clear_cart, checkout, back, place_order, accept_bounty_handler, refresh_bounties, mark_delivery_picked_up, mark_delivery_done, mark_delivery_completed
from handlers.router import router

def main():
    app = Application.builder().token(BOT_TOKEN).build();
    app.add_handler(CommandHandler("start", start));
    # text router handles menu commands
    app.add_handler(MessageHandler(filters.TEXT, router));
    
    # callback routing rules
    app.add_handler(CallbackQueryHandler(vendor_selected, pattern=r"^vendor:"));
    app.add_handler(CallbackQueryHandler(food_selected, pattern=r"^food:"));
    app.add_handler(CallbackQueryHandler(add_to_cart, pattern=r"^cart_add:"));
    app.add_handler(CallbackQueryHandler(view_cart, pattern=r"^view_cart$"));
    app.add_handler(CallbackQueryHandler(clear_cart, pattern=r"^clear_cart$"));
    app.add_handler(CallbackQueryHandler(checkout, pattern=r"^checkout$"));
    app.add_handler(CallbackQueryHandler(back, pattern=r"^back$"));
    app.add_handler(CallbackQueryHandler(place_order, pattern=r"^place_order$"));
    app.add_handler(CallbackQueryHandler(accept_bounty_handler, pattern=r"^bounty_accept:"));
    app.add_handler(CallbackQueryHandler(refresh_bounties, pattern=r"^bounties_refresh$"));
    app.add_handler(CallbackQueryHandler(mark_delivery_picked_up, pattern=r"^delivery_pickup:"));
    app.add_handler(CallbackQueryHandler(mark_delivery_done, pattern=r"^delivery_done:"));
    app.add_handler(CallbackQueryHandler(mark_delivery_completed, pattern=r"^delivery_complete:"));
    print("daizoubot is running...");
    app.run_polling();
    
    
# command handler handles /<command>
# message handler handles keyboard text
# callback handler handles inline clicks

    
if __name__ == "__main__": main();