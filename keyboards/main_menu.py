from telegram import ReplyKeyboardMarkup

def main_menu(user, is_admin=False):
    
    # maybe implement user-specific stuff later
    
    keyboard = [
    ["Browse Menu"],
    ["Available Bounties"],
    ["My Orders"],
    ["My Profile"]
    ]
    
    if (is_admin):
        # potentially keyboard.append([...]);
        pass;
    
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True);