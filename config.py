import os
from dotenv import load_dotenv

load_dotenv();

BOT_TOKEN = os.getenv("BOT_TOKEN");
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME");
MONGO_URI = os.getenv("MONGO_URI");
MAX_ACTIVE_BOUNTIES = int(os.getenv("MAX_ACTIVE_BOUNTIES", "1"));