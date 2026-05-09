from loguru import logger
from app.core.broker import broker
from app.services.temp_model import TempModelService

@broker.task(task_name="cleanup_expired_temp_models")
async def cleanup_expired_temp_models():
    """
    Background task to clean up expired temporary user models.
    """
    count = await TempModelService().cleanup_expired()
    logger.info(f"[Tasks] Cleaned up {count} expired temp models")
