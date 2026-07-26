from datetime import UTC, datetime

from pymongo import MongoClient
from pymongo.errors import PyMongoError

from config import MONGO_DB_NAME, MONGO_URI


_client = None;

# get orders table / mongo collection
# _<name> : internal helper function for this module specifically (orders)
def _get_collection():
    # ignore if no config (developing on local rn)
    if not MONGO_URI or not MONGO_DB_NAME:
        return None

    # monolithic client
    global _client
    if _client is None:
        # if doesn't exist, make it
        _client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=1000)

    # MongoDB[Database Name = MONGO_DB_NAME][Collection Name = "orders"];
    return _client[MONGO_DB_NAME]["orders"];

# create order
def create_order(user_id, cart):
    # above internal function
    collection = _get_collection()
    if collection is None or not user_id or not cart:
        return None;

    # aggregation
    items = [];
    total = 0.0;
    for entry in cart:
        # for each entry get food and quantity, calculate subtotal and total and stuff to append
        price = float(entry.get("food", {}).get("price", 0))
        quantity = entry.get("quantity", 0)
        # 2d.p.
        subtotal = round(price * quantity, 2)
        total += subtotal;
        items.append(
            {
                "food_id": entry.get("food", {}).get("id"),
                "name": entry.get("food", {}).get("name"),
                "price": price,
                "quantity": quantity,
                "subtotal": subtotal,
            }
        );

    # add the above calculated stuff to the order, create final doc and insert into db
    order = {
        # doc queries sensitive to types...
        "user_id": int(user_id),
        "items": items,
        "total": round(total, 2),
        "status": "placed",
        "created_at": datetime.now(UTC),
    }

    try:
        result = collection.insert_one(order)
        return result.inserted_id;
    except PyMongoError:
        return None;

# for view orders
def get_orders_by_user(user_id, limit=5):
    collection = _get_collection()
    if collection is None or not user_id:
        return []

    try:
        # res is a cursor object (address). list(res) converts it into the documents;
        res = collection.find(
            # as above, standardize
            {"user_id": int(user_id)},
            {"_id": 0},
        # -1 : descending order, newest entries first
        # not sure if the limiting is necessary, but let's just put it there for now
        ).sort("created_at", -1).limit(limit)
        # convert to list of dicts (order docs)
        return list(res);
    except PyMongoError:
        return []
