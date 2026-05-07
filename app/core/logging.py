import logging
import sys
from app.core.config import settings

def setup_logging():
    """
    Centralized logging configuration for the Luxe API Management service.
    Outputs to terminal (stdout) ONLY if settings.DEBUG is True.
    """
    if not settings.DEBUG:
        # If not DEBUG, we might want to still log to a file or a different handler,
        # but the requirement says "if the DEBUG is true logging shows else it does not".
        # So we disable logging or set it to a very high level with no handlers.
        logging.getLogger().handlers = []
        logging.getLogger().setLevel(logging.CRITICAL + 1)
        return

    # Basic configuration for development/terminal output
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )

    # Set external libraries to be less noisy
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("aio_pika").setLevel(logging.WARNING)
    logging.getLogger("aiormq").setLevel(logging.WARNING)

    root_logger = logging.getLogger()
    root_logger.info("Terminal logging initialized (DEBUG=True)")
