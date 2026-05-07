from beanie import Document, Indexed
from pydantic import Field
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from enum import Enum

class NotificationType(str, Enum):
    PUSH = "push"
    EMAIL = "email"
    IN_APP = "in_app"
    SMS = "sms"

class NotificationLog(Document):
    """Stores a log of every notification attempted or sent."""
    user_id: Optional[str] = Field(None, index=True)
    business_id: Optional[str] = Field(default=None, index=True)
    type: Optional[NotificationType] = None
    title: Optional[str] = None
    body: Optional[str] = None
    read: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict = Field(default_factory=dict)
    
    # Original fields to preserve compatibility
    notification_type: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None
    channel: Optional[str] = None
    recipient: Optional[Indexed(str)] = None
    status: Indexed(str) = "pending"
    retry_attempts: int = 0
    error_message: Optional[str] = None
    sent_at: Optional[datetime] = None

    class Settings:
        name = "notification_logs"
        indexes = [
            [("user_id", 1), ("created_at", -1)],
            [("user_id", 1), ("read", 1)],
            "recipient",
            "status",
        ]

class UserNotificationPreference(Document):
    """User-specific notification settings and device tokens."""
    user_id: Indexed(str)
    email_enabled: bool = True
    push_enabled: bool = True
    sms_enabled: bool = False
    whatsapp_enabled: bool = False
    device_tokens: List[str] = Field(default_factory=list)
    opted_out_types: List[str] = Field(default_factory=list)  # List of event types they don't want
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "user_preferences"
        indexes = [
            "user_id"
        ]

class NotificationTemplate(Document):
    """Database-managed templates for notifications."""
    name: Indexed(str)  # unique template name
    channel: Indexed(str)  # email, push, sms
    subject: Optional[str] = None
    body_html: Optional[str] = None
    body_text: Optional[str] = None
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "notification_templates"
        indexes = [
            [("name", 1), ("channel", 1)]
        ]
