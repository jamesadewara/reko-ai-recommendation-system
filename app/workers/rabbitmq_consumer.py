import json
import logging
import asyncio
import aio_pika
from app.core.config import settings
from app.workers.tasks import process_notification_event

logger = logging.getLogger(__name__)


async def on_message(message: aio_pika.IncomingMessage):
    async with message.process():
        try:
            body = message.body.decode()
            data = json.loads(body)

            event_type = data.get("event") or message.routing_key
            payload = data.get("payload") if ("payload" in data and "event" in data) else data

            logger.info(f"[RabbitMQ] Received event: {event_type}")

            # Enqueue via Taskiq (non-blocking)
            await process_notification_event.kiq(event_type, payload)

        except Exception as e:
            logger.error(f"[RabbitMQ] Error processing message: {e}")


async def start_rabbitmq_consumer():
    while True:
        try:
            connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
            channel = await connection.channel()

            exchange = await channel.declare_exchange(
                "luxe-events",
                aio_pika.ExchangeType.TOPIC,
                durable=True,
            )

            queue = await channel.declare_queue(settings.NOTIFICATION_QUEUE, durable=True)
            await queue.bind(exchange, routing_key="#")

            logger.info(
                f"[RabbitMQ] Consumer started. Listening on 'luxe-events' → queue: {settings.NOTIFICATION_QUEUE}"
            )

            await queue.consume(on_message)
            await asyncio.Future()  # Keep alive

        except Exception as e:
            logger.error(f"[RabbitMQ] Connection failed: {e}. Retrying in 5s...")
            await asyncio.sleep(5)
