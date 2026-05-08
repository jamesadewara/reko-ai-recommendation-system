from pymongo import AsyncMongoClient
from beanie import init_beanie
from app.documents.chat import ChatSession


async def init_db(mongo_uri: str, db_name: str) -> AsyncMongoClient:
    """
    Initialises pymongo AsyncMongoClient (pymongo >= 4.9) and Beanie ODM.
    Returns the client so it can be closed during shutdown.
    """
    client = AsyncMongoClient(mongo_uri)
    await init_beanie(
        database=client[db_name],
        document_models=[ChatSession]
    )
    return client