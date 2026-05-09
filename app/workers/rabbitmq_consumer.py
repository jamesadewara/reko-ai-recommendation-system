import json
import asyncio
import aio_pika
from loguru import logger
from app.core.config import settings
from app.tasks.search_tasks import create_user_profile, deep_search_user
from app.tasks.analysis_tasks import analyze_user_data
from app.tasks.review_tasks import generate_review_async
from app.tasks.temp_model_tasks import cleanup_expired_temp_models

# Task name to function mapping
TASK_MAP = {
    "create_user_profile": create_user_profile,
    "deep_search_user": deep_search_user,
    "analyze_user_data": analyze_user_data,
    "generate_review_async": generate_review_async,
    "cleanup_expired_temp_models": cleanup_expired_temp_models,
}

async def on_message(message: aio_pika.IncomingMessage):
    async with message.process():
        try:
            body = message.body.decode()
            data = json.loads(body)

            # Taskiq protocol or direct JSON
            task_name = data.get("task_name") or message.routing_key
            payload = data.get("args", {}) if "task_name" in data else data

            logger.info(f"[RabbitMQ] Received task: {task_name}")

            if task_name in TASK_MAP:
                task_func = TASK_MAP[task_name]
                # Enqueue via Taskiq for execution
                await task_func.kiq(payload)
                logger.info(f"[RabbitMQ] Routed {task_name} to Taskiq")
            else:
                logger.warning(f"[RabbitMQ] Unknown task: {task_name}")

        except Exception as e:
            logger.error(f"[RabbitMQ] Error processing message: {e}")


async def start_rabbitmq_consumer():
    while True:
        try:
            connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
            channel = await connection.channel()

            exchange = await channel.declare_exchange(
                "reko-events",
                aio_pika.ExchangeType.TOPIC,
                durable=True,
            )

            # We can use a specific queue for events or bind to all
            queue = await channel.declare_queue("reko-event-queue", durable=True)
            await queue.bind(exchange, routing_key="#")

            logger.info(
                f"[RabbitMQ] Consumer started. Listening on 'reko-events' → queue: reko-event-queue"
            )

            await queue.consume(on_message)
            await asyncio.Future()  # Keep alive

        except Exception as e:
            logger.error(f"[RabbitMQ] Connection failed: {e}. Retrying in 5s...")
            await asyncio.sleep(5)
