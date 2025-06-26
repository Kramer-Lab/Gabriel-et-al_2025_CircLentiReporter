import logging
import os
import socket
from logging.handlers import RotatingFileHandler


class ContextFilter(logging.Filter):
    def filter(self, record):
        record.user = os.getlogin()  # Get current OS username
        record.hostname = socket.gethostname()  # Get hostname
        return True  # Must return True to allow logging

class SafeRotatingFileHandler(RotatingFileHandler):
    """A custom FileHandler that ignores permission errors and prevents crashes."""
    def emit(self, record):
        try:
            super().emit(record)  # Try normal logging
        except (OSError, PermissionError) as e:
            print(f" Logging error: {e}. Switching to console logging.")  # Log error to console
            print(f'  {record.getMessage()}')


#create a logger
logger = logging.getLogger("TM_post_logger")
logger.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - [User: %(user)s @ %(hostname)s] - %(message)s")

# create/access log files
main_dir = os.path.dirname(os.path.abspath(__file__))
log_dir = os.path.join(main_dir, "logs")
os.makedirs(log_dir, exist_ok=True)
main_log_file = os.path.join(log_dir,"main.log")
error_log_file = os.path.join(log_dir,"errors.log")

# General log handler (appends)
general_handler = SafeRotatingFileHandler(main_log_file, maxBytes=10**7, backupCount=2)
general_handler.setLevel(logging.DEBUG)
general_handler.setFormatter(formatter)

# Error log handler (appends)
error_handler = SafeRotatingFileHandler(error_log_file, maxBytes=10**7, backupCount=2)
error_handler.setLevel(logging.ERROR)  # Only log error events
error_handler.setFormatter(formatter)

# Add handlers to logger
logger.addFilter(ContextFilter())
logger.addHandler(general_handler)
logger.addHandler(error_handler)

logger.info(f"System started by {os.getlogin()} on {socket.gethostname()} "
            f"with IP: {socket.gethostbyname(socket.gethostname())}")