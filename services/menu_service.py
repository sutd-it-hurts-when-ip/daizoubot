from pymongo import MongoClient
from pymongo.errors import PyMongoError

from config import MONGO_DB_NAME, MONGO_URI
from services.fake_db import vendors


_client = None


def _get_collection():
    if not MONGO_URI or not MONGO_DB_NAME: return None

    global _client
    if _client is None: _client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=1000)

    return _client[MONGO_DB_NAME]["vendors"];


def get_vendors():
    collection = _get_collection();
    if collection is None:
        return vendors;

    try:
        mongo_vendors = list(collection.find({}, {"_id": 0}));
        return mongo_vendors if mongo_vendors else vendors;
    except PyMongoError:
        # fallback. Remove? 
        return vendors;


def get_vendor(vendor_id):
    for vendor in get_vendors():
        if vendor.get("id") == vendor_id: return vendor

    return None;


def get_food(food_id):
    for vendor in get_vendors():
        for food in vendor.get("foods", []):
            if food.get("id") == food_id: return food

    return None;