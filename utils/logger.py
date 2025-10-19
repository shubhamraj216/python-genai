"""
Logging configuration with file rotation and automatic cleanup.
Keeps logs for 10 days with daily rotation.
"""
import os
import logging
import time
from logging.handlers import TimedRotatingFileHandler
from datetime import datetime, timedelta
from pathlib import Path


# Create logs directory
LOGS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
os.makedirs(LOGS_DIR, exist_ok=True)

LOG_FILE = os.path.join(LOGS_DIR, "app.log")
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
LOG_RETENTION_DAYS = 10


def cleanup_old_logs(directory: str, retention_days: int = LOG_RETENTION_DAYS):
    """Remove log files older than retention_days."""
    try:
        now = datetime.now()
        cutoff = now - timedelta(days=retention_days)
        
        log_dir = Path(directory)
        if not log_dir.exists():
            return
        
        deleted_count = 0
        for log_file in log_dir.glob("app.log.*"):
            if log_file.is_file():
                # Try to parse date from filename (format: app.log.YYYY-MM-DD)
                try:
                    date_str = log_file.name.replace("app.log.", "")
                    file_date = datetime.strptime(date_str, "%Y-%m-%d")
                    
                    # If file is older than retention period, delete it
                    if file_date < cutoff:
                        log_file.unlink()
                        deleted_count += 1
                        logging.info(f"Deleted old log file: {log_file.name} (age: {(now - file_date).days} days)")
                except ValueError:
                    # If filename doesn't match expected format, fall back to mtime
                    mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
                    if mtime < cutoff:
                        log_file.unlink()
                        deleted_count += 1
                        logging.info(f"Deleted old log file: {log_file.name}")
                except Exception as e:
                    logging.error(f"Failed to delete log file {log_file.name}: {e}")
        
        if deleted_count > 0:
            logging.info(f"Cleaned up {deleted_count} old log file(s)")
    except Exception as e:
        logging.error(f"Error during log cleanup: {e}")


def setup_logger(name: str = "app", level: int = logging.INFO) -> logging.Logger:
    """
    Set up logger with file rotation and console output.
    
    Args:
        name: Logger name
        level: Logging level (default: INFO)
    
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    
    # Avoid adding handlers multiple times
    if logger.handlers:
        return logger
    
    logger.setLevel(level)
    
    # File handler with daily rotation, keeping backups for 10 days
    file_handler = TimedRotatingFileHandler(
        LOG_FILE,
        when="midnight",  # Rotate at midnight
        interval=1,  # Every 1 day
        backupCount=LOG_RETENTION_DAYS,  # Keep 10 days of logs
        encoding="utf-8",
        utc=True
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
    
    # Console handler for development
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(levelname)s - %(message)s", "%H:%M:%S")
    )
    
    # Add handlers
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    # Run cleanup on startup
    cleanup_old_logs(LOGS_DIR, LOG_RETENTION_DAYS)
    
    return logger


def get_logger(name: str = None) -> logging.Logger:
    """
    Get a logger instance.
    
    Args:
        name: Logger name (if None, returns the root app logger)
    
    Returns:
        Logger instance
    """
    if name is None:
        return logging.getLogger("app")
    return logging.getLogger(f"app.{name}")


# Create default application logger
app_logger = setup_logger("app", logging.INFO)


# Log startup message
app_logger.info("=" * 80)
app_logger.info("Application logger initialized")
app_logger.info(f"Log directory: {LOGS_DIR}")
app_logger.info(f"Log file: {LOG_FILE}")
app_logger.info(f"Log retention: {LOG_RETENTION_DAYS} days")
app_logger.info("=" * 80)

