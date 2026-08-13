from telegram import Update
from telegram.ext import ContextTypes
from datetime import datetime
from keyboards.inline_menu import vendor_keyboard, food_keyboard, food_detail_keyboard, cart_keyboard, empty_card_keyboard, checkout_keyboard, bounty_keyboard, delivery_status_keyboard
from services.menu_service import get_vendors, get_vendor, get_food
from services.cart_service import add_to_cart as cart_add, get_cart, format_cart, clear_cart as cart_clear, cart_total
from services.orders_service import create_order, get_orders_by_user, get_open_bounties, accept_bounty, get_bounties_by_rider, mark_order_picked_up, mark_order_delivered, mark_order_completed
from services.payment_service import create_payment_request, is_payment_verified, mark_payment_paid

async def browse_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    vendors = get_vendors();
    # if cart has stuff, show quick button
    show_view_cart = bool(get_cart(context)) if hasattr(context, "user_data") else False
    await update.message.reply_text(
        "Select a vendor:",
        reply_markup = vendor_keyboard(vendors, show_view_cart=show_view_cart)
    )
    
# async handler
async def vendor_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    # ack callback quickly
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
    if food is None:
        await query.edit_message_text("Food not found");
        return;

    try:
        price_text = f"${float(food.get('price', 0)):0.2f}"
    except (TypeError, ValueError):
        price_text = "$0.00";

    description = food.get("description") or "No description available.";
    await query.edit_message_text(
        text=f"{food['name']}\n\nPrice: {price_text}\n{description}",
        reply_markup=food_detail_keyboard(food['id']),
    );
    
async def add_to_cart(update, context):
    query = update.callback_query
    # await query.answer();
    
    _, food_id = query.data.split(":");
    food = get_food(int(food_id))
    
    if food is None:
        await query.edit_message_text("Food not found");
        return;
      
    cart_add(context, food);
    item_quantity = 1
    for item in get_cart(context):
        if item.get("food", {}).get("id") == food.get("id"):
            item_quantity = item.get("quantity", 0)
            break

    await query.answer(text=f"Added {food['name']} to cart ({item_quantity} in cart)", show_alert=False);
    
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
        price = float(food.get('price', 0))
        quantity = i.get('quantity', 0)
        subtotal = price * quantity
        text += f"{food.get('name', 'Unknown item')}\n"
        text += f"{quantity} x ${price:.2f} = ${subtotal:.2f}\n\n"
    text += f"\nTotal: ${cart_total(context):.2f}";
    await query.edit_message_text(text = text, reply_markup = checkout_keyboard());
    
    
async def back(update, context):
    query = update.callback_query
    await query.answer();
    
    vendors = get_vendors();
    # if cart is not empty, show view cart button 
    show_view_cart = bool(get_cart(context)) if hasattr(context, "user_data") else False
    await query.edit_message_text(
        text="Choose a vendor: ",
        reply_markup=vendor_keyboard(vendors, show_view_cart=show_view_cart),
    );
    
async def place_order(update, context):
    # callback context
    query = update.callback_query;
    # stop loading spinner
    await query.answer();

    # guard empty cart
    cart = get_cart(context);
    if not cart:
        await query.edit_message_text("Your cart is empty");
        return;

    # payment then order creation
    user = update.effective_user
    user_id = user.id if user else None;
    total_amount = cart_total(context)
    payment = create_payment_request(user_id, total_amount)
    if not payment:
        await query.edit_message_text("Payment service is unavailable. Please try again later.")
        return

    # fake gateway instant success path
    paid = mark_payment_paid(payment.get("payment_id"))
    if not paid or not is_payment_verified(payment.get("payment_id")):
        await query.edit_message_text("Payment was not completed. Order cancelled.")
        return

    created = create_order(user_id, cart, payment_transaction_id=payment.get("payment_id"));
    if not created:
        await query.edit_message_text("Unable to place order right now.")
        return

    # cleanup cart
    cart_clear(context);
    await query.edit_message_text("Your order has been placed");


async def view_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # fetch user orders
    user = update.effective_user;
    user_id = user.id if user else None;
    orders = get_orders_by_user(user_id);

    # empty history branch
    if not orders:
        await update.message.reply_text("You have no orders yet.");
        return;

    # format list for chat output
    lines = ["Recent orders:"]
    for i, order in enumerate(orders, start=1):
        created_at = order.get("created_at")
        # timestamp display fallback
        if isinstance(created_at, datetime): created_text = created_at.strftime("%Y-%m-%d %H:%M")
        else: created_text = "unknown time"

        total = order.get("total", 0)
        item_count = sum(item.get("quantity", 0) for item in order.get("items", []))
        status = order.get("status", "unknown")
        lines.append(f"{i}. {created_text} | {item_count} item(s) | ${total} | {status}")

    await update.message.reply_text("\n".join(lines))


def _format_bounty_summary(order):
    item_count = sum(item.get("quantity", 0) for item in order.get("items", []))
    return f"Order {order.get('order_id')}\nItems: {item_count}\nTotal: ${order.get('total', 0)}\nStatus: {order.get('status', 'placed')}"


async def view_bounties(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bounties = get_open_bounties();
    if not bounties:
        await update.message.reply_text("No available bounties right now.");
        return;

    await update.message.reply_text("Available bounties:", reply_markup=bounty_keyboard(bounties));


async def accept_bounty_handler(update, context):
    query = update.callback_query
    await query.answer()

    _, order_id = query.data.split(":", 1)
    user = update.effective_user
    rider_id = user.id if user else None

    order = accept_bounty(order_id, rider_id);
    if not order:
        await query.edit_message_text("This bounty is no longer available.");
        return;

    await query.edit_message_text(
        "Bounty accepted.\n\n" + _format_bounty_summary(order),
        reply_markup=delivery_status_keyboard(order["order_id"], order.get("status")),
    )


async def refresh_bounties(update, context):
    query = update.callback_query
    await query.answer()

    bounties = get_open_bounties();
    if not bounties:
        await query.edit_message_text("No available bounties right now.");
        return;

    await query.edit_message_text("Available bounties:", reply_markup=bounty_keyboard(bounties));


async def mark_delivery_picked_up(update, context):
    query = update.callback_query
    await query.answer()

    _, order_id = query.data.split(":", 1)
    user = update.effective_user
    rider_id = user.id if user else None

    order = mark_order_picked_up(order_id, rider_id);
    if not order:
        await query.edit_message_text("Unable to mark this order as picked up.");
        return;

    await query.edit_message_text(
        "Order picked up.\n\n" + _format_bounty_summary(order),
        reply_markup=delivery_status_keyboard(order["order_id"], order.get("status")),
    )


async def mark_delivery_done(update, context):
    query = update.callback_query
    await query.answer()

    _, order_id = query.data.split(":", 1)
    user = update.effective_user
    rider_id = user.id if user else None

    order = mark_order_delivered(order_id, rider_id);
    if not order:
        await query.edit_message_text("Unable to mark this order as delivered.");
        return;

    await query.edit_message_text(
        "Order delivered.\n\n" + _format_bounty_summary(order),
        reply_markup=delivery_status_keyboard(order["order_id"], order.get("status")),
    )


# rider confirms fulfillment is complete
async def mark_delivery_completed(update, context):
    query = update.callback_query
    await query.answer()

    _, order_id = query.data.split(":", 1)
    user = update.effective_user
    rider_id = user.id if user else None

    order = mark_order_completed(order_id, rider_id);
    if not order:
        await query.edit_message_text("Unable to mark this order as completed.");
        return;

    await query.edit_message_text(
        "Order completed. Bounty will be closed after 3 minutes and payout will be processed.\n\n"
        + _format_bounty_summary(order),
        reply_markup=delivery_status_keyboard(order["order_id"], order.get("status")),
    )


async def view_accepted_bounties(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user;
    rider_id = user.id if user else None;
    # get bounties for rider
    bounties = get_bounties_by_rider(rider_id);

    if not bounties:
        await update.message.reply_text("You have not accepted any bounties yet.");
        return;

    # only actionable statuses
    actionable = [bounty for bounty in bounties if bounty.get("status") in {"accepted", "picked_up"}];

    # no active work branch
    if not actionable:
        await update.message.reply_text("You have no active accepted bounties.");
        return;

    # render each active bounty
    await update.message.reply_text("Accepted bounties:");
    for bounty in actionable:
        await update.message.reply_text(
            _format_bounty_summary(bounty),
            reply_markup=delivery_status_keyboard(bounty.get("order_id"), bounty.get("status")),
        )