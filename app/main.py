import logging
import asyncio
from datetime import datetime, timezone
from contextlib import asynccontextmanager
import logging
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.db import init_db
from app.core.broker import init_broker, shutdown_broker
from fastapi.responses import HTMLResponse
from app.core.config import settings
from app.core.logging import setup_logging

# Initialize logging as soon as possible
setup_logging()

from app.api.v1.endpoints.authentication import router as authentication_router
from fastapi import Depends

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──
    logger.info("🚀 [Lifespan] Starting up Reko AI System")
    
    try:
        # 1. Initialize Database (Native PyMongo AsyncMongoClient via Beanie)
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
        logger.info("🛑 [Lifespan] Shutting down Reko AI System...")
        
        # 1. Shutdown TaskIQ
        await shutdown_broker()
        
        # 2. Close MongoDB
        if hasattr(app.state, "mongo_client"):
            app.state.mongo_client.close()
            logger.info("✅ [Database] MongoDB connection closed.")
            
        logger.info("🏁 [Lifespan] Cleanup complete.")


app = FastAPI(
    title=settings.APP_NAME,
    description="Reko AI Authentication System - Manages user accounts, authentication, and authorization for the Reko ecosystem.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url=None,       # disabled — served manually below to avoid CDN blocking
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
# ── Health Check ──────────────────────────────────────────────────────────────
@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "reko-ai-system"}

@app.get("/", include_in_schema=False)
async def root():
    return {"message": "Reko AI System is running", "version": "1.0.0"}

@app.get("/redoc", include_in_schema=False)
async def redoc_html():
    # Serves ReDoc using unpkg CDN instead of jsdelivr.net
    # jsdelivr is blocked by Edge/Safari tracking prevention
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

app.include_router(authentication_router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(ws_router, prefix="/api/v1/notifications", tags=["websocket"])