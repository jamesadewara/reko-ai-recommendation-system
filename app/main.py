import sys
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse
from loguru import logger

from app.core.config import settings
from app.core.logging import setup_logging
from app.db.session import init_db
from app.core.broker import init_broker, shutdown_broker
from app.core.middleware import RateLimitMiddleware, RequestIDMiddleware

# Initialize logging as soon as possible
setup_logging()

# Import Routers
# Import Routers
from app.api.v1.endpoints.chats import router as chats_router
from app.api.v1.endpoints.websocket import router as ws_router
from app.api.v1.endpoints.search import router as search_router
from app.api.v1.endpoints.users import router as users_router
from app.api.v1.endpoints.reviews import router as reviews_router
from app.api.v1.endpoints.recommendations import router as recommendations_router
from app.api.v1.endpoints.ads import router as ads_router
# from app.api.v1.endpoints.items import router as items_router

# Import tasks to ensure they are registered
import app.tasks.search_tasks
import app.tasks.analysis_tasks
import app.tasks.review_tasks
import app.tasks.temp_model_tasks

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──
    logger.info(f"🚀 [Lifespan] Starting up {settings.APP_NAME}")
    
    try:
        # 1. Initialize Database (MongoDB via Beanie)
        logger.info("🔗 [Database] Connecting to MongoDB...")
        app.state.mongo_client = await init_db(
            settings.DATABASE_URL, 
            settings.DATABASE_NAME
        )
        logger.info("✅ [Database] MongoDB connected and Beanie initialized.")
        
        # 2. Initialize TaskIQ Broker
        logger.info("📡 [TaskIQ] Initializing broker...")
        await init_broker()
        logger.info("✅ [TaskIQ] Broker ready.")

        # 3. Load ML Models
        logger.info("🧠 [ML] Loading spaCy model...")
        import spacy
        try:
            app.state.nlp = spacy.load(settings.SPACY_MODEL)
            logger.info(f"✅ [ML] spaCy model {settings.SPACY_MODEL} loaded.")
        except Exception as e:
            logger.error(f"❌ [ML] Failed to load spaCy model: {e}")

        logger.info("🧠 [ML] Loading SentenceTransformer model...")
        from app.services.embedding_encoder import get_encoder
        try:
            # This populates the singleton in the embedding_encoder module
            app.state.embedding_model = get_encoder()
            logger.info(f"✅ [ML] SentenceTransformer {settings.SENTENCE_TRANSFORMER_MODEL} loaded.")
        except Exception as e:
            logger.error(f"❌ [ML] Failed to load SentenceTransformer model: {e}")
            
        logger.info("🔍 [FAISS] Initializing Vector Search Index...")
        from app.ml.faiss_manager import get_faiss_index
        try:
            await get_faiss_index()
            logger.info("✅ [FAISS] Vector Search Index ready.")
        except Exception as e:
            logger.error(f"❌ [FAISS] Failed to initialize FAISS index: {e}")
        
        logger.info("✨ [Lifespan] Server ready to handle requests.")
        yield
        
    except Exception as e:
        logger.error(f"❌ [Lifespan] CRITICAL ERROR during startup: {e}")
        raise
    
    finally:
        # ── Shutdown ──
        logger.info(f"🛑 [Lifespan] Shutting down {settings.APP_NAME}...")
        
        # 1. Shutdown TaskIQ
        await shutdown_broker()
        
        # 2. Close MongoDB
        if hasattr(app.state, "mongo_client"):
            app.state.mongo_client.close()
            logger.info("✅ [Database] MongoDB connection closed.")
            
        logger.info("🏁 [Lifespan] Cleanup complete.")

 
app = FastAPI(
    title=settings.APP_NAME,
    description="Reko AI Recommendation System - Handles product analysis, user preferences, and real-time AI chat.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url=None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(RequestIDMiddleware)

# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health_check():
    return {
        "status": "ok", 
        "service": settings.APP_NAME,
        "services": ["mongodb", "rabbitmq"]
    }

@app.get("/", include_in_schema=False)
async def root():
    return {"message": f"{settings.APP_NAME} is running", "version": "1.0.0"}

@app.get("/redoc", include_in_schema=False)
async def redoc_html():
    return HTMLResponse(f"""
<!DOCTYPE html>
<html>
  <head>
    <title>{settings.APP_NAME} - API Docs</title>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>body {{ margin: 0; padding: 0; }}</style>
  </head>
  <body>
    <redoc spec-url="/openapi.json"></redoc>
    <script src="https://unpkg.com/redoc@latest/bundles/redoc.standalone.js"></script>
  </body>
</html>
""")

# Register API Routers
app.include_router(chats_router, prefix="/api/v1/chats", tags=["Chats"])
app.include_router(ws_router, prefix="/api/v1/ws", tags=["WebSocket"])
app.include_router(search_router, prefix="/api/v1/search", tags=["Deep Search"])
app.include_router(users_router, prefix="/api/v1/users", tags=["Users"])
app.include_router(reviews_router, prefix="/api/v1/reviews", tags=["Reviews"])
app.include_router(recommendations_router, prefix="/api/v1/recommendations", tags=["Recommendations"])
app.include_router(ads_router, prefix="/api/v1/ads", tags=["Ads"])

# Serve Static Files
from fastapi.staticfiles import StaticFiles
import os

static_path = "app/static"
if not os.path.exists(static_path):
    os.makedirs(static_path, exist_ok=True)

app.mount("/static", StaticFiles(directory=static_path), name="static")