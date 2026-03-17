"""
Production-Ready Logging System

This module provides centralized logging configuration for the entire backend.

Features:
- Structured JSON logging for production
- Human-readable colored logs for development
- Automatic log rotation (prevents disk overflow)
- Request ID tracking for distributed tracing
- Performance metrics logging
- Separate error log file
- Integration with cloud logging services (Sentry, CloudWatch)

Why centralized logging:
- Consistent log format across all components
- Easy to parse logs for monitoring/alerting
- Trace requests across services
- Debug production issues
- Compliance audit trail
"""

import logging
import logging.handlers
import sys
import json
import traceback
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path
import os

# LOG LEVELS CONFIGURATION

LOG_LEVELS = {
    "DEBUG": logging.DEBUG,      
    "INFO": logging.INFO,       
    "WARNING": logging.WARNING,  
    "ERROR": logging.ERROR,      
    "CRITICAL": logging.CRITICAL 
}

# CUSTOM JSON FORMATTER (For Production)

class JSONFormatter(logging.Formatter):
    """
    Formats logs as JSON for structured logging.
    
    Why JSON:
    - Easy to parse by log aggregators (ELK, Datadog, CloudWatch)
    - Searchable fields (level, component, request_id)
    - Machine-readable for alerting
    
    Output example:
    {
        "timestamp": "2025-12-26T10:15:30.123Z",
        "level": "ERROR",
        "component": "livekit_handler",
        "message": "Deepgram connection failed",
        "request_id": "req-abc123",
        "interview_id": 456,
        "stack_trace": "Traceback...",
        "environment": "production"
    }
    """
    
    def format(self, record: logging.LogRecord) -> str:
        """Convert log record to JSON string"""
        
        # Base log entry
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "component": record.name,
            "message": record.getMessage(),
            "environment": os.getenv("ENVIRONMENT", "development"),
        }
        
        # Add request ID if available (for tracing)
        if hasattr(record, "request_id"):
            log_entry["request_id"] = record.request_id
        
        # Add interview ID if available (for filtering)
        if hasattr(record, "interview_id"):
            log_entry["interview_id"] = record.interview_id
        
        # Add candidate email if available
        if hasattr(record, "candidate_email"):
            log_entry["candidate_email"] = record.candidate_email
        
        # Add duration for performance metrics
        if hasattr(record, "duration_ms"):
            log_entry["duration_ms"] = record.duration_ms
        
        # Add stack trace for errors
        if record.exc_info:
            log_entry["stack_trace"] = self.formatException(record.exc_info)
        
        # Add extra fields (anything passed via extra={} in log call)
        if hasattr(record, "extra_fields"):
            log_entry.update(record.extra_fields)
        
        return json.dumps(log_entry)

# COLORED FORMATTER (For Development)

class ColoredFormatter(logging.Formatter):
    """
    Adds colors to console logs for better readability in development.
    
    Why colors:
    - Quickly spot errors (red) vs info (green)
    - Better developer experience
    - Easier debugging in local terminal
    """
    
    # ANSI color codes
    COLORS = {
        "DEBUG": "\033[36m",      # Cyan
        "INFO": "\033[32m",       # Green
        "WARNING": "\033[33m",    # Yellow
        "ERROR": "\033[31m",      # Red
        "CRITICAL": "\033[35m",   # Magenta
        "RESET": "\033[0m"        # Reset
    }
    
    # Emoji for visual distinction
    EMOJI = {
        "DEBUG": "🔍",
        "INFO": "ℹ️ ",
        "WARNING": "⚠️ ",
        "ERROR": "❌",
        "CRITICAL": "🔥"
    }
    
    def format(self, record: logging.LogRecord) -> str:
        """Add colors and emoji to log message"""
        
        # Get color and emoji
        color = self.COLORS.get(record.levelname, self.COLORS["RESET"])
        emoji = self.EMOJI.get(record.levelname, "")
        reset = self.COLORS["RESET"]
        
        # Format timestamp
        timestamp = datetime.fromtimestamp(record.created).strftime("%H:%M:%S.%f")[:-3]
        
        # Format component name (logger name)
        component = f"[{record.name}]".ljust(25)
        
        # Build colored log line
        log_line = (
            f"{color}{emoji} {timestamp}{reset} "
            f"{color}{component}{reset} "
            f"{record.getMessage()}"
        )
        
        # Add stack trace for exceptions
        if record.exc_info:
            log_line += f"\n{self.formatException(record.exc_info)}"
        
        return log_line

# LOGGER SETUP FUNCTION

def setup_logging(
    component_name: str = "supegroww",
    log_level: Optional[str] = None,
    log_to_file: bool = True
) -> logging.Logger:
    """
    Set up and configure a logger.
    
    Args:
        component_name: Name of the component (e.g., "livekit_handler", "api")
        log_level: Override default log level
        log_to_file: Whether to write logs to file
    
    Returns:
        Configured logger instance
    
    Usage:
        ```python
        from logger import setup_logging
        
        logger = setup_logging("livekit_handler")
        logger.info("Starting interview")
        logger.error("Connection failed", extra={"interview_id": 123})
        ```
    """

    env = os.getenv("ENVIRONMENT", "development")
    default_level = os.getenv("LOG_LEVEL", "INFO")
    log_dir_path = os.getenv("LOG_DIR", "./logs")
    should_log_to_file = os.getenv("LOG_TO_FILE", "True").lower() == "true"
    sentry_dsn = os.getenv("SENTRY_DSN")

    # Create logger
    logger = logging.getLogger(component_name)
    
    # Set level
    level = log_level or default_level
    logger.setLevel(LOG_LEVELS.get(level, logging.INFO))
    
    # Remove existing handlers (prevents duplicate logs)
    logger.handlers.clear()
    
    # CONSOLE HANDLER
    
    console_handler = logging.StreamHandler(sys.stdout)
    
    # Use colored formatter in development, JSON in production
    if env == "development":
        console_formatter = ColoredFormatter()
    else:
        console_formatter = JSONFormatter()
    
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # FILE HANDLERS (Only in production or if explicitly enabled)
    
    if log_to_file and should_log_to_file:
        # Create logs directory
        log_dir = Path(log_dir_path)
        log_dir.mkdir(parents=True, exist_ok=True)
        
        # 1. ALL LOGS (Rotating file handler)
        all_logs_path = log_dir / f"{component_name}.log"
        
        # RotatingFileHandler prevents disk overflow
        # maxBytes=10MB, backupCount=5 means max 50MB of logs
        file_handler = logging.handlers.RotatingFileHandler(
            all_logs_path,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,  # Keep 5 old files
            encoding="utf-8"
        )
        file_handler.setFormatter(JSONFormatter())
        logger.addHandler(file_handler)
        
        # 2. ERROR LOGS (Separate file for errors only)
        error_logs_path = log_dir / f"{component_name}.error.log"
        
        error_handler = logging.handlers.RotatingFileHandler(
            error_logs_path,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding="utf-8"
        )
        error_handler.setLevel(logging.ERROR)  
        error_handler.setFormatter(JSONFormatter())
        logger.addHandler(error_handler)
    
    # SENTRY INTEGRATION (For error tracking in production)
    
    if sentry_dsn:
        try:
            import sentry_sdk
            from sentry_sdk.integrations.logging import LoggingIntegration
            
            sentry_logging = LoggingIntegration(
                level=logging.INFO,        # Capture info and above
                event_level=logging.ERROR  # Send errors as Sentry events
            )
            
            sentry_sdk.init(
                dsn=sentry_dsn,
                integrations=[sentry_logging],
                environment=env,
                traces_sample_rate=0.1,  # 10% of transactions
            )
            
            logger.info("✅ Sentry error tracking enabled")
        
        except ImportError:
            logger.warning("⚠️  sentry-sdk not installed, error tracking disabled")
    
    return logger

# CONTEXT LOGGER (For Request Tracing)

class ContextLogger:
    """
    Logger with automatic context propagation.
    
    Why:
    - Automatically adds request_id to all logs
    - Tracks interview_id across components
    - Enables distributed tracing
    
    Usage:
        ```python
        context_logger = ContextLogger(
            logger=logger,
            request_id="req-abc123",
            interview_id=456
        )
        
        context_logger.info("Processing started")
        # Output includes: {"request_id": "req-abc123", "interview_id": 456, ...}
        ```
    """
    
    def __init__(
        self,
        logger: logging.Logger,
        request_id: Optional[str] = None,
        interview_id: Optional[int] = None,
        **extra_context
    ):
        self.logger = logger
        self.context = {
            "request_id": request_id,
            "interview_id": interview_id,
            **extra_context
        }
        # Remove None values
        self.context = {k: v for k, v in self.context.items() if v is not None}
    
    def _log(self, level: int, message: str, **kwargs):
        """Internal log method that adds context"""
        extra = kwargs.get("extra", {})
        extra.update(self.context)
        kwargs["extra"] = extra
        self.logger.log(level, message, **kwargs)
    
    def debug(self, message: str, **kwargs):
        self._log(logging.DEBUG, message, **kwargs)
    
    def info(self, message: str, **kwargs):
        self._log(logging.INFO, message, **kwargs)
    
    def warning(self, message: str, **kwargs):
        self._log(logging.WARNING, message, **kwargs)
    
    def error(self, message: str, **kwargs):
        self._log(logging.ERROR, message, **kwargs)
    
    def critical(self, message: str, **kwargs):
        self._log(logging.CRITICAL, message, **kwargs)

# PERFORMANCE LOGGER (For Timing)

class PerformanceLogger:
    """
    Context manager for logging execution time.
    
    Why:
    - Track slow operations
    - Identify bottlenecks
    - Monitor API response times
    
    Usage:
        ```python
        with PerformanceLogger(logger, "database_query"):
            result = db.query(User).all()
        
        # Logs: "database_query completed in 123.45ms"
        ```
    """
    
    def __init__(
        self,
        logger: logging.Logger,
        operation_name: str,
        **context
    ):
        self.logger = logger
        self.operation_name = operation_name
        self.context = context
        self.start_time = None
    
    def __enter__(self):
        self.start_time = datetime.utcnow()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        end_time = datetime.utcnow()
        duration = (end_time - self.start_time).total_seconds() * 1000  # ms
        
        extra = {
            "duration_ms": round(duration, 2),
            "operation": self.operation_name,
            **self.context
        }
        
        if exc_type:
            self.logger.error(
                f"{self.operation_name} failed after {duration:.2f}ms",
                extra=extra,
                exc_info=(exc_type, exc_val, exc_tb)
            )
        else:
            self.logger.info(
                f"{self.operation_name} completed in {duration:.2f}ms",
                extra=extra
            )

# CONVENIENCE FUNCTIONS

def get_logger(component_name: str) -> logging.Logger:
    """
    Get or create a logger for a component.
    
    This is the main function you'll use throughout the codebase.
    
    Usage:
        ```python
        from logger import get_logger
        
        logger = get_logger("api.candidates")
        logger.info("Creating candidate")
        ```
    """
    return setup_logging(component_name)


def log_request(logger: logging.Logger, request, duration_ms: float):
    """
    Log HTTP request details.
    
    Usage:
        ```python
        from logger import log_request
        
        @app.middleware("http")
        async def log_requests(request: Request, call_next):
            start = time.time()
            response = await call_next(request)
            duration = (time.time() - start) * 1000
            log_request(logger, request, duration)
            return response
        ```
    """
    logger.info(
        f"{request.method} {request.url.path}",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status_code": getattr(request.state, "status_code", None),
            "duration_ms": round(duration_ms, 2),
            "client_ip": request.client.host if request.client else None
        }
    )


def log_exception(
    logger: logging.Logger,
    exc: Exception,
    context: Optional[Dict[str, Any]] = None
):
    """
    Log exception with full context.
    
    Usage:
        ```python
        try:
            risky_operation()
        except Exception as e:
            log_exception(logger, e, {"interview_id": 123})
            raise
        ```
    """
    logger.error(
        f"Exception occurred: {type(exc).__name__}: {str(exc)}",
        exc_info=True,
        extra={"extra_fields": context or {}}
    )

# INITIALIZE ROOT LOGGER

# Set up root logger on module import
root_logger = setup_logging("supegroww")

# EXAMPLE USAGE

if __name__ == "__main__":
    """Test the logging system"""
    
    # 1. Basic logging
    logger = get_logger("test")
    
    logger.debug("This is a debug message")
    logger.info("Interview started successfully")
    logger.warning("API rate limit approaching")
    logger.error("Database connection failed")
    
    # 2. Logging with context
    logger.info("Processing candidate", extra={
        "interview_id": 123,
        "candidate_email": "alice@example.com"
    })
    
    # 3. Context logger
    ctx_logger = ContextLogger(
        logger,
        request_id="req-abc123",
        interview_id=456
    )
    ctx_logger.info("This log automatically includes request_id and interview_id")
    
    # 4. Performance logging
    with PerformanceLogger(logger, "test_operation"):
        import time
        time.sleep(0.1)  
    
    # 5. Exception logging
    try:
        raise ValueError("Test error")
    except Exception as e:
        log_exception(logger, e, {"interview_id": 789})