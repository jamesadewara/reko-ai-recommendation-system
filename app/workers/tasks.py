import logging
from datetime import datetime, timezone

from app.core.broker import broker
from app.utils.email import send_templated_email
from app.utils.firebase import send_push_notification

logger = logging.getLogger(__name__)


# ── Email Task ────────────────────────────────────────────────────────────────

@broker.task
async def send_email_task(recipient: str, subject: str, template_name: str, context: dict):
    logger.info(f"Sending email to {recipient} using template {template_name}")
    try:
        send_templated_email(recipient, subject, template_name, context)
    except Exception as exc:
        logger.error(f"Error sending email to {recipient}: {exc}")
        raise


# ── Push Notification Task ────────────────────────────────────────────────────

@broker.task
async def send_push_notification_task(token: str, title: str, body: str, data: dict = None):
    logger.info(f"Sending push notification to token: {token}")
    try:
        send_push_notification(token, title, body, data)
    except Exception as exc:
        logger.error(f"Error sending push notification: {exc}")
        raise


# ── Main Event Router Task ────────────────────────────────────────────────────

@broker.task
async def process_notification_event(event_type: str, payload: dict):
    """
    Routes an incoming event to the appropriate notification channels.

    Beanie is already initialized via the Taskiq worker startup hook in
    main.py — so all Document models are safe to use here directly with
    no asyncio bridging or re-initialization needed.
    """
    from app.documents.notification import NotificationLog, UserNotificationPreference, NotificationTemplate
    
    # ── Lazy Init Check (Emergency) ──────────────────────────────────────────
    try:
        NotificationLog.get_settings().name
    except Exception:
        from app.core.broker import worker_startup
        await worker_startup()

    logger.info(f"[Worker] Processing event: {event_type}")

    email = payload.get("email") or payload.get("user_email")
    user_id = payload.get("user_id")

    # ── 1. Fetch User Preferences ─────────────────────────────────────────────
    prefs = None
    if user_id:
        prefs = await UserNotificationPreference.find_one({"user_id": str(user_id)})

    # ── 2. Determine Channels ─────────────────────────────────────────────────
    send_email = bool(email)
    send_push = "push_token" in payload

    if prefs:
        if event_type in prefs.opted_out_types:
            logger.info(f"[Worker] User {user_id} opted out of {event_type}")
            return
        send_email = send_email and prefs.email_enabled
        send_push = send_push and prefs.push_enabled

    # ── 3. Handle Email ───────────────────────────────────────────────────────
    if send_email:
        subject_map = {
            "user.registered": "Welcome to LUXE!",
            "password.reset.requested": "Reset Your Password",
            "otp": "Your Verification Code",
            "otp.generated": "Your Verification Code",
            "staff.invited": "You've been invited as Staff",
            "account.deactivated": "Your LUXE account has been deactivated",
            "reactivation_otp": "LUXE Account Reactivation",
            "payment.refund_requested": "Refund Request Received",
            "payment.confirmed": "Payment Confirmed! 🥂",
            "underage": "Account Restriction: Age Policy",
        }
        template_map = {
            "user.registered": "welcome.html",
            "otp": "verify_otp.html",
            "otp.generated": "verify_otp.html",
            "password.reset.requested": "password_reset.html",
            "staff.invited": "staff_invite.html",
            "account.deactivated": "account_deactivated.html",
            "reactivation_otp": "verify_otp.html",
            "payment.refund_requested": "refund_requested.html",
            "payment.confirmed": "payment_confirmed.html",
            "underage": "underage_restriction.html",
        }

        subject = subject_map.get(event_type, "New Notification from LUXE")
        template_name = template_map.get(event_type, f"{event_type.replace('.', '_')}.html")

        # DB template subject override
        db_template = await NotificationTemplate.find_one(
            {"name": event_type, "channel": "email", "is_active": True}
        )
        if db_template and db_template.subject:
            subject = db_template.subject

        await send_email_task.kiq(email, subject, template_name, payload)
        logger.info(f"[Worker] Email task enqueued → {email} for {event_type}")

    # ── 4. Handle Push ────────────────────────────────────────────────────────
    if send_push:
        token = payload["push_token"]
        title = "New Notification"
        body = f"You have a new {event_type} notification."
        await send_push_notification_task.kiq(token, title, body, payload)
        logger.info(f"[Worker] Push task enqueued for {event_type}")

    # ── 5. Log to MongoDB via Beanie ──────────────────────────────────────────
    try:
        log = NotificationLog(
            channel="multi",
            recipient=email or user_id or "unknown",
            notification_type=event_type,
            payload=payload,
            status="processed",
            sent_at=datetime.now(timezone.utc),
        )
        await log.insert()
    except Exception as log_err:
        logger.error(f"[Worker] Failed to write notification log: {log_err}")
