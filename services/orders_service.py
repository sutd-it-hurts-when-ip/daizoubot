from datetime import UTC, datetime, timedelta
from bson import ObjectId

from pymongo import MongoClient
from pymongo.errors import PyMongoError

from config import MAX_ACTIVE_BOUNTIES, MONGO_DB_NAME, MONGO_URI
from services.payment_service import record_delivery_payment
from services.user_service import get_user_by_uid


_client = None;

# extract _id field from OrderId() object
def _normalize_order(order):
    if not order: return None

    # cast order to dictionary
    normalized = dict(order)
    # rename and empty _id handling
    if "_id" in normalized: normalized["order_id"] = str(normalized.pop("_id"));
    else: normalized["order_id"] = "unknown ID";
    return normalized

# get orders table / mongo collection
# _<name> : internal helper function for this module specifically (orders)
def _get_collection():
    # ignore if no config (developing on local rn)
    if not MONGO_URI or not MONGO_DB_NAME: return None

    # monolithic client
    global _client
    if _client is None:
        # if doesn't exist, make it
        _client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=1000);

    # MongoDB[Database Name = MONGO_DB_NAME][Collection Name = "orders"];
    return _client[MONGO_DB_NAME]["orders"];

# create order
def create_order(user_id, cart, payment_transaction_id=None):
    # above internal function
    collection = _get_collection()
    if collection is None or not user_id or not cart:
        return None;

    # get profile snapshot, if doesn't exist, just reeturn None
    profile = get_user_by_uid(user_id)
    if not profile: return None

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
        "orderer_profile": {
            "uid": int(profile.get("uid", user_id)),
            "username": profile.get("username"),
            "student_id": profile.get("student_id"),
        },
        "items": items,
        "total": round(total, 2),
        "status": "placed",
        "created_at": datetime.now(UTC),
    }

    if payment_transaction_id: order["payment_transaction_id"] = str(payment_transaction_id)

    try:
        result = collection.insert_one(order)
        return result.inserted_id;
    except PyMongoError:
        return None;

# for view orders
def get_orders_by_user(user_id, limit=5):
    collection = _get_collection();
    if collection is None or not user_id: return []

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
        return [];


def get_open_bounties(limit=10):
    collection = _get_collection();
    if collection is None: return []

    try:
        cursor = (
            collection.find(
                {"status": "placed", "assigned_rider_id": {"$exists": False}},
                # selecting which fields to return from each matched doc
                {"user_id": 1, "items": 1, "total": 1, "created_at": 1},
            )
            .sort("created_at", 1)
            .limit(limit)
        )
        return [_normalize_order(order) for order in cursor];
    except PyMongoError:
        return [];


def get_active_delivery(rider_id):
    collection = _get_collection();
    if collection is None or not rider_id: return None

    try:
        order = collection.find_one(
            {
                "assigned_rider_id": int(rider_id),
                "status": {"$in": ["accepted", "picked_up"]},
            },
            {"user_id": 1, "items": 1, "total": 1, "status": 1, "created_at": 1},
            sort=[("accepted_at", -1), ("created_at", -1)],
        )
        return _normalize_order(order);
    except PyMongoError:
        return None;


def get_bounties_by_rider(rider_id, limit=10):
    collection = _get_collection();
    if collection is None or not rider_id: return []

    try:
        cursor = (
            collection.find(
                {
                    "assigned_rider_id": int(rider_id),
                    "status": {"$in": ["accepted", "picked_up", "delivered"]},
                },
                {"user_id": 1, "items": 1, "total": 1, "status": 1, "created_at": 1},
            )
            .sort("accepted_at", -1)
            .limit(limit)
        )
        return [_normalize_order(order) for order in cursor];
    except PyMongoError:
        return [];


def accept_bounty(order_id, rider_id):
    collection = _get_collection();
    if collection is None or not order_id or not rider_id: return None

    rider_profile = get_user_by_uid(rider_id)
    if not rider_profile: return None

    try:
        active_count = collection.count_documents(
            {
                "assigned_rider_id": int(rider_id),
                "status": {"$in": ["accepted", "picked_up"]},
            }
        )
        # weird edge-case if mocked count is not an int
        if not isinstance(active_count, int): active_count = 0
        if active_count >= int(MAX_ACTIVE_BOUNTIES): return None

        order = collection.find_one_and_update(
            {
                "_id": ObjectId(str(order_id)),
                "status": "placed",
                "assigned_rider_id": {"$exists": False},
            },
            {
                "$set": {
                    "status": "accepted",
                    "assigned_rider_id": int(rider_id),
                    "assigned_rider_profile": {
                        "uid": int(rider_profile.get("uid", rider_id)),
                        "username": rider_profile.get("username"),
                        "student_id": rider_profile.get("student_id"),
                    },
                    "accepted_at": datetime.now(UTC),
                }
            },
            return_document=True,
            projection={"user_id": 1, "items": 1, "total": 1, "status": 1, "created_at": 1},
        )
        return _normalize_order(order);
    except (PyMongoError, ValueError):
        return None;


def mark_order_picked_up(order_id, rider_id):
    collection = _get_collection();
    if collection is None or not order_id or not rider_id: return None

    try:
        order = collection.find_one_and_update(
            {
                "_id": ObjectId(str(order_id)),
                "assigned_rider_id": int(rider_id),
                "status": "accepted",
            },
            {
                "$set": {
                    "status": "picked_up",
                    "picked_up_at": datetime.now(UTC),
                }
            },
            return_document=True,
            projection={"user_id": 1, "items": 1, "total": 1, "status": 1, "created_at": 1},
        )
        return _normalize_order(order);
    except (PyMongoError, ValueError):
        return None;


def mark_order_delivered(order_id, rider_id):
    collection = _get_collection();
    if collection is None or not order_id or not rider_id: return None

    try:
        order = collection.find_one_and_update(
            {
                "_id": ObjectId(str(order_id)),
                "assigned_rider_id": int(rider_id),
                "status": "picked_up",
            },
            {
                "$set": {
                    "status": "delivered",
                    "delivered_at": datetime.now(UTC),
                }
            },
            return_document=True,
            projection={"user_id": 1, "items": 1, "total": 1, "status": 1, "created_at": 1},
        )
        return _normalize_order(order);
    except (PyMongoError, ValueError):
        return None;


# final rider status update before auto-close window
def mark_order_completed(order_id, rider_id):
    collection = _get_collection();
    if collection is None or not order_id or not rider_id: return None

    try:
        order = collection.find_one_and_update(
            {
                "_id": ObjectId(str(order_id)),
                "assigned_rider_id": int(rider_id),
                "status": "delivered",
            },
            {
                "$set": {
                    "status": "completed",
                    "completed_at": datetime.now(UTC),
                }
            },
            return_document=True,
            projection={"user_id": 1, "items": 1, "total": 1, "status": 1, "created_at": 1},
        )
        return _normalize_order(order);
    except (PyMongoError, ValueError):
        return None;


# one-time rollback for mistaken picked_up action
def retract_order_picked_up(order_id, rider_id):
    collection = _get_collection();
    if collection is None or not order_id or not rider_id: return None

    try:
        order = collection.find_one_and_update(
            {
                "_id": ObjectId(str(order_id)),
                "assigned_rider_id": int(rider_id),
                "status": "picked_up",
                "$or": [
                    {"retractions.picked_up": {"$exists": False}},
                    {"retractions.picked_up": {"$lt": 1}},
                ],
            },
            {
                "$set": {"status": "accepted"},
                "$inc": {"retractions.picked_up": 1},
            },
            return_document=True,
            projection={"user_id": 1, "items": 1, "total": 1, "status": 1, "created_at": 1},
        )
        return _normalize_order(order);
    except (PyMongoError, ValueError):
        return None;


# one-time rollback for mistaken delivered action
def retract_order_delivered(order_id, rider_id):
    collection = _get_collection();
    if collection is None or not order_id or not rider_id: return None

    try:
        order = collection.find_one_and_update(
            {
                "_id": ObjectId(str(order_id)),
                "assigned_rider_id": int(rider_id),
                "status": "delivered",
                "$or": [
                    {"retractions.delivered": {"$exists": False}},
                    {"retractions.delivered": {"$lt": 1}},
                ],
            },
            {
                "$set": {"status": "picked_up"},
                "$inc": {"retractions.delivered": 1},
            },
            return_document=True,
            projection={"user_id": 1, "items": 1, "total": 1, "status": 1, "created_at": 1},
        )
        return _normalize_order(order);
    except (PyMongoError, ValueError):
        return None;


# one-time rollback for mistaken completed action by orderer
def retract_order_completed(order_id, orderer_id):
    collection = _get_collection();
    if collection is None or not order_id or not orderer_id: return None

    try:
        order = collection.find_one_and_update(
            {
                "_id": ObjectId(str(order_id)),
                "user_id": int(orderer_id),
                "status": "completed",
                "$or": [
                    {"retractions.completed": {"$exists": False}},
                    {"retractions.completed": {"$lt": 1}},
                ],
            },
            {
                "$set": {"status": "delivered"},
                "$inc": {"retractions.completed": 1},
            },
            return_document=True,
            projection={"user_id": 1, "items": 1, "total": 1, "status": 1, "created_at": 1},
        )
        return _normalize_order(order);
    except (PyMongoError, ValueError):
        return None;


# close completed bounty after cooldown and attach payout transaction
def close_bounty(order_id, wait_minutes=3):
    collection = _get_collection();
    if collection is None or not order_id: return None

    try:
        order = collection.find_one(
            {"_id": ObjectId(str(order_id)), "status": "completed"},
            {
                "_id": 1,
                "user_id": 1,
                "assigned_rider_id": 1,
                "items": 1,
                "total": 1,
                "status": 1,
                "completed_at": 1,
                "created_at": 1,
            },
        )
        if not order: return None

        completed_at = order.get("completed_at")
        if not isinstance(completed_at, datetime): return None
        if completed_at.tzinfo is None: completed_at = completed_at.replace(tzinfo=UTC)

        # wait a bit before closing to allow for dispute / retraction if needed.
        if datetime.now(UTC) < completed_at + timedelta(minutes=wait_minutes): return None

        rider_id = order.get("assigned_rider_id")
        rider_profile = get_user_by_uid(rider_id) if rider_id is not None else None
        if not rider_profile: return None

        receiving_method_valid = bool(rider_profile.get("receiving_method_valid", True)) # default to True if not set.
        payout = record_delivery_payment(
            rider_id=rider_id,
            amount=float(order.get("total", 0)),
            source_order_id=order.get("_id"),
            receiving_method_valid=receiving_method_valid,
        )
        if not payout: return None # propogate None upwards if ppayout creation failed

        closed = collection.find_one_and_update(
            {"_id": order.get("_id"), "status": "completed"},
            {
                "$set": {
                    "status": "closed",
                    "closed_at": datetime.now(UTC),
                    "delivery_payment": payout,
                }
            },
            return_document=True,
            projection={"user_id": 1, "items": 1, "total": 1, "status": 1, "created_at": 1, "delivery_payment": 1},
        )
        return _normalize_order(closed)
    except (PyMongoError, ValueError):
        return None
