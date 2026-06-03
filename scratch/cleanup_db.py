from pymongo import MongoClient
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def list_all_users():
    DATABASE_URL = "mongodb://localhost:27017"
    DATABASE_NAME = "reko_ai_system_db"
    
    client = MongoClient(DATABASE_URL)
    db = client[DATABASE_NAME]
    users_col = db["users"]
    
    logger.info("Listing all users in 'users' collection...")
    users = list(users_col.find({}, {"email": 1, "auth_user_id": 1}))
    logger.info(f"Total users: {len(users)}")
    for u in users:
        logger.info(f"ID: {u['_id']}, Email: {u.get('email')}, AuthID: {u.get('auth_user_id')}")

if __name__ == "__main__":
    list_all_users()
