from loguru import logger
from app.core.broker import broker
from app.core.config import settings
from taskiq.schedule_sources import LabelScheduleSource

# Taskiq Scheduler configuration. 
# Run this via: taskiq scheduler app.core.broker:broker --sources app.tasks.scheduler:schedule_source

logger.info(f"[Scheduler] Configuring cleanup schedule using CRON: {settings.TEMP_MODEL_CLEANUP_CRON}")

broker.task(
    "cleanup_expired_temp_models",
    schedule=[{"cron": settings.TEMP_MODEL_CLEANUP_CRON}],
)

schedule_source = LabelScheduleSource(broker)
