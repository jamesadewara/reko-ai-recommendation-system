import logging
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from app.core.config import settings
from app.core.logging import setup_logging
from app.db.session import init_db
from app.core.broker import init_broker, shutdown_broker

# Initialize logging as soon as possible
setup_logging()

# Import Routers
from app.api.v1.endpoints.chats import router as chats_router
from app.api.v1.endpoints.websocket import router as ws_router

logger = logging.getLogger(__name__)

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
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": settings.APP_NAME}

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

# Import tasks to ensure they are registered
import app.tasks.birthday