import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def main():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client.reko_ai_system_db
    count = await db.reviews.count_documents({})
    user_count = await db.users.count_documents({})
    items_count = await db.items.count_documents({})
    print(f"Reviews: {count}")
    print(f"Users: {user_count}")
    print(f"Items: {items_count}")
    client.close()

if __name__ == "__main__":
    asyncio.run(main())
