from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from config import BOT_TOKEN
from handlers.start import start
from handlers.menu import browse_menu, vendor_selected, food_selected, add_to_cart, view_cart, clear_cart, checkout, back, place_order
from handlers.router import router

def main():
    app = Application.builder().token(BOT_TOKEN).build();
    app.add_handler(CommandHandler("start", start));
    # filters.TEXT --> only trigger if update contains text. filters.Regex --> only call if string is EXACTLY browse menu
    # app.add_handler(MessageHandler(filters.TEXT & filters.Regex("^Browse Menu$"), browse_menu));
    app.add_handler(MessageHandler(filters.TEXT, router));
    
    # give tele a rule. basically .addEventListener() in js
    app.add_handler(CallbackQueryHandler(vendor_selected, pattern=r"^vendor:"));
    app.add_handler(CallbackQueryHandler(food_selected, pattern=r"^food:"));
    app.add_handler(CallbackQueryHandler(add_to_cart, pattern=r"^cart_add:"));
    app.add_handler(CallbackQueryHandler(view_cart, pattern=r"^view_cart$"));
    app.add_handler(CallbackQueryHandler(clear_cart, pattern=r"^clear_cart$"));
    app.add_handler(CallbackQueryHandler(checkout, pattern=r"^checkout$"));
    app.add_handler(CallbackQueryHandler(back, pattern=r"^back$"));
    app.add_handler(CallbackQueryHandler(place_order, pattern=r"^place_order$"));
    print("daizoubot is running...")
    app.run_polling();
    
    
# notes
# command handler handles /<command>
# message handler handles <message> (reply keyboards)
# CallbackQueryHandler handles hidden click events (from INLINE keyboards).

    
if __name__ == "__main__": main();