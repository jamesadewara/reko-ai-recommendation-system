import os
from loguru import logger

from app.core.config import settings
from app.ml.faiss_index import FAISSIndex
from app.documents.item import ItemDocument

_faiss_index_singleton = None

async def get_faiss_index() -> FAISSIndex:
    global _faiss_index_singleton
    if _faiss_index_singleton is not None:
        return _faiss_index_singleton
        
    index = FAISSIndex(dim=384)
    if os.path.exists(settings.FAISS_INDEX_PATH):
        index.load(settings.FAISS_INDEX_PATH)
    else:
        logger.info("[FAISSManager] Index not found, attempting to build from DB...")
        items = await ItemDocument.find_all().to_list()
        index.build_from_items(items)
        index.save(settings.FAISS_INDEX_PATH)
        
    _faiss_index_singleton = index
    return _faiss_index_singleton

async def rebuild_index():
    global _faiss_index_singleton
    logger.info("[FAISSManager] Rebuilding FAISS index from DB...")
    items = await ItemDocument.find_all().to_list()
    index = FAISSIndex(dim=384)
    index.build_from_items(items)
    index.save(settings.FAISS_INDEX_PATH)
    _faiss_index_singleton = index
    logger.info("[FAISSManager] FAISS index rebuild complete.")
