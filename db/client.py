# --- IMPORTS ---
# region imports

from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import ConnectionFailure

from config import MONGO_DB_NAME, MONGO_URI

# endregion


# store single instance of mongodb client
_client: AsyncMongoClient | None = None


async def get_client() -> AsyncMongoClient:
    """
    Get MongoDB client instance.
    """

    # enforce singleton design pattern
    global _client
    if _client is None:

        # establish client
        _client = AsyncMongoClient(MONGO_URI)
    
    # check for connection failure
    try:

        await _client.admin.command("ping")

    except ConnectionFailure:

        print("[!] MongoDB server unavailable.")

    return _client


async def get_database() -> AsyncDatabase:
    """
    Get access to MongoDB database through client instance.
    """

    client = await get_client()

    return client.get_database(MONGO_DB_NAME)


async def close_client() -> None:
    """
    Close MongoDB client instance. To be called on app shutdown.
    """

    # close client instance if it exists
    global _client
    if _client is not None:

        await _client.close()
        _client = None