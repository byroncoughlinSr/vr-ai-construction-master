"""
Structured logging configuration for the VR Construction API.
"""

import logging
import sys
from typing import Dict, Any
from pythonjsonlogger import jsonlogger


class CustomJsonFormatter(jsonlogger.JsonFormatter):
    """Custom JSON formatter with additional fields."""

    def add_fields(self, log_record: Dict[str, Any], record: logging.LogRecord, message_dict: Dict[str, Any]) -> None:
        super().add_fields(log_record, record, message_dict)

        # Add custom fields
        log_record['service'] = 'vr-construction-api'
        log_record['version'] = '1.0.0'

        # Add request ID if available (will be set by middleware)
        if hasattr(record, 'request_id'):
            log_record['request_id'] = record.request_id

        # Add user ID if available
        if hasattr(record, 'user_id'):
            log_record['user_id'] = record.user_id

        # Add processing time for performance monitoring
        if hasattr(record, 'processing_time'):
            log_record['processing_time_ms'] = record.processing_time


def setup_logging(log_level: str = "INFO", json_format: bool = True) -> None:
    """
    Configure structured logging for the application.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_format: Whether to use JSON formatting for logs
    """
    # Convert string log level to logging constant
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    # Clear existing handlers
    root_logger = logging.getLogger()
    root_logger.handlers.clear()

    # Create formatter
    if json_format:
        formatter = CustomJsonFormatter(
            fmt='%(asctime)s %(name)s %(levelname)s %(service)s %(version)s %(message)s'
        )
    else:
        formatter = logging.Formatter(
            fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(numeric_level)

    # Add handler to root logger
    root_logger.addHandler(console_handler)
    root_logger.setLevel(numeric_level)

    # Set levels for noisy libraries
    logging.getLogger('uvicorn.access').setLevel(logging.WARNING)
    logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)
    logging.getLogger('httpx').setLevel(logging.WARNING)

    # Create logger for this application
    logger = logging.getLogger('app')
    logger.info("Logging configured", extra={
        'log_level': log_level,
        'json_format': json_format,
        'service': 'vr-construction-api'
    })


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with the specified name."""
    return logging.getLogger(f'app.{name}')
