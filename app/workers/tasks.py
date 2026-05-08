import logging
from datetime import datetime, timezone

from app.core.broker import broker
# from app.utils.email import send_templated_email

logger = logging.getLogger(__name__)


# ── Email Task ────────────────────────────────────────────────────────────────

# @broker.task
# async def send_email_task(recipient: str, subject: str, template_name: str, context: dict):
#     logger.info(f"Sending email to {recipient} using template {template_name}")
#     try:
#         send_templated_email(recipient, subject, template_name, context)
#     except Exception as exc:
#         logger.error(f"Error sending email to {recipient}: {exc}")
#         raise




# ── Main Event Router Task ────────────────────────────────────────────────────

# @broker.task
# async def process_notification_event(event_type: str, payload: dict):
#     """
#     Routes an incoming event to the appropriate notification channels.
#     """
#     logger.info(f"[Worker] LUXE leftover - commenting out: {event_type}")
#     pass
