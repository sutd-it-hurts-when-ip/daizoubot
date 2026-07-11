def get_cart(context):
    return context.user_data.setdefault("cart", [])
    
def add_to_cart(context, food):
    cart = get_cart(context)
    
    for i in cart:
        if i['food']['id'] == food['id']: 
            i['quantity'] += 1;
            return;
    cart.append({"food": food, "quantity": 1});

def remove_from_cart(context, food):
    cart = get_cart(context);
    
    for i in cart:
        if i['food']['id'] == food_id:
            i['quantity'] -= 1;
            if i['quantity'] <= 0:
                cart.remove(item);
            return;
            
def clear_cart(context):
    context.user_data['cart'] = [];
    
def cart_total(context):
    total = 0;
    for i in get_cart(context):
        total += i['food']['price'] * i['quantity'];
    return total;
        
def cart_item_count(context):
    count = 0;
    for i in get_cart(context):
        count += i['quantity']
    return count;
    
def format_cart(context):
    cart = get_cart(context);
    if not cart: return "Your cart is empty.";
    text = "Your cart contains " + str(cart_item_count(context)) + " items.\n\n";
    for i in cart:
        subtotal = i['food']['price'] * i['quantity'];
        text += i['food']['name'] + "\n" + str(i['food']['price']) + " * " + str(i['quantity']) + " = $" + str(subtotal) + "\n\n"
        text += "Items: " + str(cart_item_count(context));
        text += "\n"
        text += "Total = $" + str(cart_total(context));
        return text;