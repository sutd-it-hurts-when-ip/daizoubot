from telegram import Update
from telegram.ext import ContextTypes
from keyboards.inline_menu import vendor_keyboard, food_keyboard, food_detail_keyboard, cart_keyboard, empty_card_keyboard, checkout_keyboard
from services.menu_service import get_vendors, get_vendor, get_food
from services.cart_service import add_to_cart as cart_add, get_cart, format_cart, clear_cart as cart_clear, cart_total

async def browse_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    vendors = get_vendors();
    await update.message.reply_text(
        "Select a vendor:",
        reply_markup = vendor_keyboard(vendors)
    )
    
# async: function returns a coroutine. Like in Unity.
async def vendor_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    # like yield, but event-driven
    await query.answer()
    # debug
    print(query.data);
    kind, vendor_id = query.data.split(":");
    vendor = get_vendor(int(vendor_id));
    await query.edit_message_text(text = "" + vendor['name'] + " Menu", reply_markup = food_keyboard(vendor['foods']))
 
async def food_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer();
    kind, food_id = query.data.split(":")
     
    # await query.edit_message_text(food_id);
    food = get_food(int(food_id))
    await query.edit_message_text(text="" + food['name'] + "\n\n" + str(food['price']) + "\n" + food['description'], reply_markup=food_detail_keyboard(food['id']));
    
async def add_to_cart(update, context):
    query = update.callback_query
    # await query.answer();
    
    _, food_id = query.data.split(":");
    food = get_food(int(food_id))
    
    if food is None:
        await query.edit_message_text("Food not found");
        return;
      
    cart_add(context, food);
    print(get_cart(context));
    await query.answer(text="Added " + food['name'] + " to cart", show_alert=False);
    
async def view_cart(update, context):
    # debug
    print("viewCart called")

    query = update.callback_query
    await query.answer()
    cart = get_cart(context);
    
    # debug
    print(cart);
        
    if cart: keyboard = cart_keyboard();
    if not cart: keyboard = empty_card_keyboard();
    await query.edit_message_text(text=format_cart(context), reply_markup = keyboard);
    
async def clear_cart(update, context):
    query = update.callback_query;
    await query.answer();
    cart_clear(context);
    await query.edit_message_text("Your cart is empty", reply_markup = empty_card_keyboard());
    
async def checkout(update, context):
    query = update.callback_query;
    await query.answer();
    
    cart = get_cart(context)
    
    if not cart:
        await query.edit_message_text("Your cart is empty");
        return;
        
    text = "Checkout\n\n";
    for i in cart:
        food = i['food']
        subtotal = food['price'] * i['quantity']
        text += food['name']
        text += '\n'
        text += str(i['quantity']) + " * " + str(food['price'])
        text += " = $" + str(subtotal);
    text += "\nTotal: $" + str(cart_total(context));
    await query.edit_message_text(text = text, reply_markup = checkout_keyboard());
    
    
async def back(update, context):
    query = update.callback_query
    await query.answer();
    
    vendors = get_vendors();
    await query.edit_message_text(text="Choose a vendor: ", reply_markup = vendor_keyboard(vendors));
    
async def place_order(update, context):
    #temp
    query = update.callback_query;
    await query.answer();
    cart_clear(context);
    await query.edit_message_text("Your order has been placed");