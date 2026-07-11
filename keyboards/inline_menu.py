from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)


def vendor_keyboard(vendors):

    keyboard = [];
    for v in vendors:
        keyboard.append([InlineKeyboardButton(v["name"], callback_data=f"vendor:{v['id']}")]);

    return InlineKeyboardMarkup(keyboard)
    
def food_keyboard(foods):
    
    keyboard = [];
    for f in foods:
        # there's no handling for weird data 
        keyboard.append([InlineKeyboardButton("" + f["name"] + ": $" + str(f['price']) + ".", callback_data=f"food:{f['id']}")]);
        
    return InlineKeyboardMarkup(keyboard);
    
def food_detail_keyboard(food_id):
    keyboard = [
        [InlineKeyboardButton("Add to Cart", callback_data=f"cart_add:{food_id}")],
        [InlineKeyboardButton("View Cart", callback_data="view_cart")],
        [InlineKeyboardButton("Back", callback_data="back")]
    ]

    return InlineKeyboardMarkup(keyboard)
    
def cart_keyboard():
    keyboard = [
        [InlineKeyboardButton("Checkout", callback_data="checkout")],
        [InlineKeyboardButton("Clear Cart", callback_data="clear_cart")],
        [InlineKeyboardButton("Continue Shopping", callback_data="back")]
    ]
    
    return InlineKeyboardMarkup(keyboard);
    
def empty_card_keyboard():
    keyboard = [[InlineKeyboardButton("Browse Menu", callback_data="back")]];
    return InlineKeyboardMarkup(keyboard);
    
def checkout_keyboard():
    keyboard = [
        [InlineKeyboardButton("Place Order", callback_data="place_order")],
        [InlineKeyboardButton("Cancel", callback_data="view_cart")]
    ]
    
    return InlineKeyboardMarkup(keyboard);
    