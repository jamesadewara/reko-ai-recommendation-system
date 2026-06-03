import asyncio
from app.db.session import init_db
from app.documents.item import ItemDocument
from app.core.config import settings

async def check():
    await init_db(settings.DATABASE_URL, settings.DATABASE_NAME)
    items = await ItemDocument.find_all().to_list()
    print(f"Total Items: {len(items)}")
    for i in items[:10]:
        print(f"- {i.name} ({i.category})")

if __name__ == "__main__":
    asyncio.run(check())
