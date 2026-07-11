# temp
from services.fake_db import vendors

def get_vendors():
    # temp
    return vendors;
    
    # also temp
def get_vendor(vendor_id):
    for vendor in vendors:
        if vendor["id"] == vendor_id:
            return vendor

    return None
    
def get_food(food_id):
    for vendor in vendors:
        for food in vendor["foods"]:
            if food["id"] == food_id:
                return food

    return None