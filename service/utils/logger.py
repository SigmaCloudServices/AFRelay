import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.propagate = False

if not logger.hasHandlers():
    project_root = Path(__file__).resolve().parents[2]
    log_dir = Path(os.getenv("AFRELAY_LOG_DIR", str(project_root / "logs")))
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file_name = os.getenv("AFRELAY_LOG_FILE", "afrelay.log")
    log_path = log_dir / log_file_name

    max_bytes = int(os.getenv("AFRELAY_LOG_MAX_BYTES", "10485760"))
    backup_count = int(os.getenv("AFRELAY_LOG_BACKUP_COUNT", "5"))

    handler = RotatingFileHandler(
        log_path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)

__all__ = ["logger"]
