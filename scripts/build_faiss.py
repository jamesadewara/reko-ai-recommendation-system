import asyncio
import os
import sys
from loguru import logger

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.db.session import init_db
from app.core.config import settings
from app.ml.faiss_manager import rebuild_index

async def main():
    logger.info("🚀 Starting FAISS Index Build...")
    await init_db(settings.DATABASE_URL, settings.DATABASE_NAME)
    
    await rebuild_index()
    logger.info("✅ FAISS Index build completed successfully!")

if __name__ == "__main__":
    asyncio.run(main())
