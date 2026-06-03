import sys
from loguru import logger
from app.core.config import settings

def setup_logging():
    """
    Centralized logging configuration for Reko AI.
    Outputs to terminal (stdout) ONLY if settings.DEBUG is True.
    """
    # Remove all existing handlers
    logger.remove()

    if settings.DEBUG:
        # Configure loguru for terminal output
        logger.add(
            sys.stdout,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
            level="INFO",
            colorize=True
        )
        logger.info("Terminal logging initialized (DEBUG=True) via Loguru")
    else:
        # In production (non-DEBUG), we might want to log only ERROR/CRITICAL
        # but the user requested "if the DEBUG is true logging shows else it does not"
        pass
