from datetime import UTC, datetime, timedelta

from bson import ObjectId
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from config import MONGO_DB_NAME, MONGO_URI
from services.user_service import get_user_by_uid


_client = None

# same as others
def _get_collection():
    # skip db ops if env not ready
    if not MONGO_URI or not MONGO_DB_NAME: return None

    global _client
    if _client is None: _client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=1000)

    return _client[MONGO_DB_NAME]["payments"];

# create payment request for user, returns None if something went wrong (DB down, invalid args, etc)
def create_payment_request(user_id, amount):
    collection = _get_collection();
    if collection is None or not user_id: return None

    profile = get_user_by_uid(user_id)
    if not profile: return None

    try:
        payment_id = str(ObjectId()); now = datetime.now(UTC)
        doc = {
            "payment_id": payment_id,
            "user_id": int(user_id),
            "username": profile.get("username"),
            "student_id": profile.get("student_id"),
            "amount": round(float(amount), 2),
            "status": "pending",
            "qr_payload": f"FAKEPAY:{payment_id}",
            "created_at": now,
            "expires_at": now + timedelta(minutes=5),
            "paid_at": None,
        }
        collection.insert_one(doc);
        return {
            "payment_id": payment_id,
            "status": "pending",
            "qr_payload": doc["qr_payload"],
            "expires_at": doc["expires_at"],
        };
    except (PyMongoError, ValueError, TypeError):
        return None;


def mark_payment_paid(payment_id):
    collection = _get_collection();
    if collection is None or not payment_id: return None

    try:
        now = datetime.now(UTC)
        payment = collection.find_one_and_update(
            {
                "payment_id": str(payment_id),
                "status": "pending",
                "expires_at": {"$gt": now},
            },
            {
                "$set": {
                    "status": "paid",
                    "paid_at": now,
                }
            },
            return_document=True,
            projection={"_id": 0}, # intentionally exclude _id from returned doc
        )
        return payment;
    except PyMongoError:
        return None;


def mark_payment_expired(payment_id):
    collection = _get_collection();
    if collection is None or not payment_id: return None

    try:
        payment = collection.find_one_and_update(
            {"payment_id": str(payment_id), "status": "pending"},
            {"$set": {"status": "expired", "expires_at": datetime.now(UTC)}},
            return_document=True,
            projection={"_id": 0},
        )
        return payment;
    except PyMongoError:
        return None;

# basically jsut check if payment exists & mark as paid
def is_payment_verified(payment_id):
    collection = _get_collection();
    if collection is None or not payment_id: return False

    try:
        payment = collection.find_one(
            {"payment_id": str(payment_id), "status": "paid"},
            {"_id": 0, "payment_id": 1},
        )
        return payment is not None;
    except PyMongoError:
        return False;


# record payout to rider after bounty closes
def record_delivery_payment(rider_id, amount, source_order_id, receiving_method_valid=True):
    collection = _get_collection();
    if collection is None or not rider_id: return None

    profile = get_user_by_uid(rider_id)
    if not profile: return None

    try:
        payment_id = str(ObjectId()); now = datetime.now(UTC)
        # payout status flips to pending if receiving method is invalid
        status = "paid_out" if receiving_method_valid else "pending_balance"
        doc = {
            "payment_id": payment_id,
            "payment_type": "delivery_payout",
            "source_order_id": str(source_order_id),
            "user_id": int(rider_id),
            "username": profile.get("username"),
            "student_id": profile.get("student_id"),
            "amount": round(float(amount), 2),
            "status": status,
            "created_at": now,
            # handle edge case where receiving method invalid
            "paid_at": now if status == "paid_out" else None,
            "reason": None if status == "paid_out" else "invalid_receiving_method",
        }
        collection.insert_one(doc);
        return {
            "payment_id": payment_id,
            "status": status,
            "reason": doc.get("reason"),
            "amount": doc["amount"],
        };
    except (PyMongoError, ValueError, TypeError):
        return None;