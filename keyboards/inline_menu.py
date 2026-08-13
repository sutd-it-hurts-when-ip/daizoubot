from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)


def vendor_keyboard(vendors, show_view_cart=False):

    keyboard = [];
    for v in vendors:
        # skip malformed rows
        vendor_name = v.get("name") if isinstance(v, dict) else None
        vendor_id = v.get("id") if isinstance(v, dict) else None
        if vendor_name is None or vendor_id is None: continue
        keyboard.append([InlineKeyboardButton(vendor_name, callback_data=f"vendor:{vendor_id}")]);

    if show_view_cart: keyboard.append([InlineKeyboardButton("View Cart", callback_data="view_cart")]);

    return InlineKeyboardMarkup(keyboard);
    
def food_keyboard(foods):
    
    keyboard = [];
    for f in foods:
        # skip malformed rows
        food_name = f.get("name") if isinstance(f, dict) else None
        food_price = f.get("price") if isinstance(f, dict) else None
        food_id = f.get("id") if isinstance(f, dict) else None
        if food_name is None or food_price is None or food_id is None: continue
        try:
            price_text = f"${float(food_price):.2f}"
        except (TypeError, ValueError):
            continue
        keyboard.append([InlineKeyboardButton(f"{food_name}: {price_text}", callback_data=f"food:{food_id}")]);
        
    return InlineKeyboardMarkup(keyboard);
    
def food_detail_keyboard(food_id):
    keyboard = [
        [InlineKeyboardButton("Add to Cart", callback_data=f"cart_add:{food_id}")],
        [InlineKeyboardButton("View Cart", callback_data="view_cart")],
        [InlineKeyboardButton("Back", callback_data="back")]
    ]

    return InlineKeyboardMarkup(keyboard);
    
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


def bounty_keyboard(bounties):
    keyboard = [];
    for bounty in bounties:
        item_count = sum(item.get("quantity", 0) for item in bounty.get("items", []));
        label = f"Accept {item_count} item(s) | ${bounty.get('total', 0)}";
        keyboard.append([InlineKeyboardButton(label, callback_data=f"bounty_accept:{bounty['order_id']}")]);

    keyboard.append([InlineKeyboardButton("Refresh", callback_data="bounties_refresh")]);
    return InlineKeyboardMarkup(keyboard);


def delivery_status_keyboard(order_id, status):
    # status-driven action button
    if status == "accepted": keyboard = [[InlineKeyboardButton("Mark Picked Up", callback_data=f"delivery_pickup:{order_id}")]]
    elif status == "picked_up": keyboard = [[InlineKeyboardButton("Mark Delivered", callback_data=f"delivery_done:{order_id}")]]
    elif status == "delivered": keyboard = [[InlineKeyboardButton("Mark Completed", callback_data=f"delivery_complete:{order_id}")]]
    else: keyboard = []

    keyboard.append([InlineKeyboardButton("Back to Bounties", callback_data="bounties_refresh")]);
    return InlineKeyboardMarkup(keyboard);
    