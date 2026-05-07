import json
import logging
import asyncio
import aio_pika
from typing import Optional, Callable, Awaitable, Any
from app.core.config import settings

logger = logging.getLogger(__name__)

class RekoAiEventBus:
    """
    Standardized RabbitMQ Event Bus for the Luxe platform.
    Supports robust publishing and subscribing to the common topic exchange.
    """
    def __init__(self):
        self.connection: Optional[aio_pika.RobustConnection] = None
        self.channel: Optional[aio_pika.RobustChannel] = None
        self.exchange: Optional[aio_pika.RobustExchange] = None
        self._exchange_name = "luxe-events"

    async def connect(self):
        """Establish a robust connection and declare common exchange."""
        if self.connection and not self.connection.is_closed:
            return

        try:
            self.connection = await aio_pika.connect_robust(
                settings.RABBITMQ_URL,
                timeout=10,
                client_properties={"connection_name": settings.APP_NAME}
            )
            self.channel = await self.connection.channel()
            # Declare the main topic exchange for inter-service communication
            self.exchange = await self.channel.declare_exchange(
                self._exchange_name,
                aio_pika.ExchangeType.TOPIC,
                durable=True
            )
            logger.info(f"[RabbitMQ] Connected to '{self._exchange_name}' exchange")
        except Exception as e:
            logger.error(f"[RabbitMQ] Connection failed: {e}")
            raise

    async def publish(self, routing_key: str, payload: dict):
        """Publish a message to the exchange with persistent delivery."""
        if not self.exchange:
            await self.connect()

        try:
            message_body = json.dumps(payload, default=str).encode()
            message = aio_pika.Message(
                body=message_body,
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                content_type="application/json",
                app_id=settings.APP_NAME
            )
            await self.exchange.publish(message, routing_key=routing_key)
            logger.debug(f"[RabbitMQ] Published '{routing_key}'")
        except Exception as e:
            logger.error(f"[RabbitMQ] Publish failed: {e}")

    async def start_consuming(self, queue_name: str, routing_key: str, callback: Callable[[dict], Awaitable[None]]):
        """Standardized consumer loop with prefetch and robust binding."""
        if not self.channel:
            await self.connect()

        try:
            await self.channel.set_qos(prefetch_count=1)
            queue = await self.channel.declare_queue(queue_name, durable=True)
            await queue.bind(self.exchange, routing_key=routing_key)
            
            logger.info(f"[RabbitMQ] Subscribed to '{routing_key}' via '{queue_name}'")

            async with queue.iterator() as queue_iter:
                async for message in queue_iter:
                    async with message.process():
                        try:
                            payload = json.loads(message.body.decode())
                            await callback(payload)
                        except Exception as e:
                            logger.error(f"[RabbitMQ] Processing error on '{routing_key}': {e}")
        except Exception as e:
            logger.error(f"[RabbitMQ] Consumption failed: {e}")

    async def close(self):
        """Graceful shutdown of the RabbitMQ connection."""
        if self.connection:
            await self.connection.close()
            logger.info("[RabbitMQ] Connection closed")

# Global instance for app-wide use
event_bus = RekoAiEventBus()
