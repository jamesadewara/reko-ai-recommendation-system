from pymongo import AsyncMongoClient
from beanie import init_beanie
from app.documents.notification import NotificationLog, UserNotificationPreference, NotificationTemplate

async def init_db(mongo_uri: str, db_name: str):
    """
    Initializes Beanie ODM using the standard PyMongo AsyncMongoClient.
    """
    client = AsyncMongoClient(mongo_uri)
    await init_beanie(
        database=client[db_name],
        document_models=[NotificationLog, UserNotificationPreference, NotificationTemplate]
    )
    return client