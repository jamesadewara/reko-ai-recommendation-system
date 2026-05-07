import logging
from app.core.config import settings

logger = logging.getLogger(__name__)

# ── Broker ─────────────────────────────────────────────────────────────────────
# We define the broker here, but we connect it inside the lifespan to avoid blocking.
broker = PubSubBroker(settings.RABBITMQ_URL).with_result_backend(result_backend)

async def init_broker():
    """
    Asynchronously connect the TaskIQ broker.
    Called inside the FastAPI lifespan.
    """
    logger.info("[TaskIQ] Connecting broker...")
    try:
        await broker.startup()
        logger.info("[TaskIQ] Broker connected successfully.")
    except Exception as e:
        logger.error(f"[TaskIQ] Failed to connect broker: {e}")
        raise

async def shutdown_broker():
    """
    Gracefully shutdown the TaskIQ broker.
    """
    logger.info("[TaskIQ] Shutting down broker...")
    try:
        await broker.shutdown()
        logger.info("[TaskIQ] Broker shutdown complete.")
    except Exception as e:
        logger.error(f"[TaskIQ] Error during broker shutdown: {e}")
