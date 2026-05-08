import logging
from app.core.broker import broker

logger = logging.getLogger(__name__)

@broker.task(task_name="handle_birthday_event")
async def handle_birthday_event(user_id: str, email: str):
    """
    Handles birthday events received from the Auth System via RabbitMQ.
    """
    logger.info(f"[Tasks] Received birthday event for user {user_id} ({email})")
    
    # 1. Wish the user (could be a notification, internal log, etc.)
    logger.info(f"[Tasks] Happy Birthday to user {user_id}!")
    
    # 2. Prepare special birthday recommendations
    # This is where you would call your recommendation engine
    logger.info(f"[Tasks] Preparing special birthday recommendations for user {user_id}...")
    
    # Mock logic: update user's recommendation state or send a push notification
    # ...
    
    logger.info(f"[Tasks] Birthday processing for user {user_id} complete.")
