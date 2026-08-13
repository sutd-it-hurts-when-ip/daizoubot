import re
from datetime import UTC, datetime

from pymongo import MongoClient
from pymongo.errors import PyMongoError

from config import MONGO_DB_NAME, MONGO_URI


_client = None


def _get_collection():
    if not MONGO_URI or not MONGO_DB_NAME:
        return None

    global _client
    if _client is None:
        _client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=1000)

    return _client[MONGO_DB_NAME]["users"]

# check that input is valid
def is_valid_student_id(student_id):
    if not isinstance(student_id, str): # check that input is a string
        return False

    return bool(re.fullmatch(r"\d{7}", student_id.strip())) # and then check that it's a 7 digit number (or one digit 7 times)

# get user profile by uid, returns None if not found or error
def get_user_by_uid(uid):
    collection = _get_collection()
    if collection is None or not uid:
        return None

    try:
        return collection.find_one({"uid": int(uid)}, {"_id": 0})
    except PyMongoError:
        return None

# check if user has registered account
def has_registered_account(uid):
    collection = _get_collection()
    if collection is None:
        # Fail-open in local/no-DB mode so core bot flows still work.
        return True

    if not uid:
        return False

    try:
        return collection.find_one({"uid": int(uid)}, {"_id": 1}) is not None
    except PyMongoError:
        return False

# create user
def create_user_account(uid, username, student_id):
    collection = _get_collection()
    # if args invalid or collection is None (DB not ready), or something went wrong, return None.
    if collection is None or not uid or not username or not is_valid_student_id(student_id):
        return None

    # don't use has_registered_account() here - if DB is down, account will be registered as True,
    # it will treat the user as registered and skip creation, which could cause potential issues.
    try:
        existing = collection.find_one({"uid": int(uid)}, {"_id": 0})
        if existing:
            return existing

        doc = {
            "uid": int(uid),
            "username": str(username).strip(),
            "student_id": student_id.strip(),
            "created_at": datetime.now(UTC),
        }
        collection.insert_one(doc)
        return collection.find_one({"uid": int(uid)}, {"_id": 0})
    except PyMongoError:
        return None