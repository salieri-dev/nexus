import sys
from typing import List

import structlog
from structlog.types import Processor, EventDict

import logging


def drop_color_message_key(_, __, event_dict: EventDict) -> EventDict:
    event_dict.pop("color_message", None)
    return event_dict


def setup_structlog(json_logs: bool = False, log_level: str = "INFO", log_file: str = "frontend.log"):
    timestamper = structlog.processors.TimeStamper(fmt="iso")

    shared_processors: List[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.stdlib.ExtraAdder(),
        drop_color_message_key,
        timestamper,
        structlog.processors.StackInfoRenderer(),
    ]

    structlog.configure(
        processors=shared_processors
                   + [
                       structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
                   ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    console_formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.dev.ConsoleRenderer(colors=True),
        ],
    )

    json_formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors
                          + [
                              structlog.processors.format_exc_info,
                          ],
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(),
        ],
    )

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(console_formatter)

    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(json_formatter if json_logs else console_formatter)

    root_logger = logging.getLogger()
    root_logger.addHandler(stream_handler)
    root_logger.addHandler(file_handler)
    root_logger.setLevel(log_level.upper())

    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        root_logger.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))

    sys.excepthook = handle_exception

    return structlog.get_logger()
