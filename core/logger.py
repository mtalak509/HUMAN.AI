import sys

from loguru import logger


def setup_logging(level: str = "INFO", json_mode: bool = False) -> None:
    """
    Настраивает loguru global singleton.
    Вызывается один раз в lifespan.
    """
    logger.remove()

    if json_mode:
        logger.add(
            sys.stderr,
            level=level,
            serialize=True,
        )
    else:
        logger.add(
            sys.stderr,
            level=level,
            format=(
                "<green>{time:HH:mm:ss}</green> | "
                "<level>{level:<8}</level> | "
                "<cyan>{name}:{line}</cyan> | "
                "<level>{message}</level>"
            ),
            colorize=True,
        )
