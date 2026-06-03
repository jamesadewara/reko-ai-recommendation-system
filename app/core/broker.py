import logging
from taskiq_aio_pika import AioPikaBroker
from taskiq import TaskiqEvents

from app.core.config import settings

logger = logging.getLogger(__name__)

# ── Broker ─────────────────────────────────────────────────────────────────────
# RabbitMQ broker for Taskiq (No Redis)
broker = AioPikaBroker(
    settings.RABBITMQ_URL,
    queue_name="recommendation_queue"
)

@broker.on_event(TaskiqEvents.WORKER_STARTUP)
async def worker_startup(state):
    """
    Initialize connections when worker starts.
    """
    from app.db.session import init_db
    from app.core.config import settings
    await init_db(settings.DATABASE_URL, settings.DATABASE_NAME)
    logger.info("[TaskIQ] Worker started and DB initialized.")

async def init_broker():
    """
    Connect broker during app startup.
    """
    await broker.startup()
    logger.info("[TaskIQ] Broker initialized.")

async def shutdown_broker():
    """
    Gracefully disconnect.
    """
    await broker.shutdown()
    logger.info("[TaskIQ] Broker shutdown.")

# Import tasks to ensure they are registered with the broker
# for discovery by the worker process.
import app.tasks.search_tasks
import app.tasks.analysis_tasks
import app.tasks.review_tasks
import app.tasks.temp_model_tasks
