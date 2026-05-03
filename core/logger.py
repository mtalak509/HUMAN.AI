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
            format="{time:HH:mm:ss} | {level:<8} | {name}:{line} | {message}",
            colorize=True,
        )
