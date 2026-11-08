"""Writable analysis paths; the source tree stays read-only in hosted deployments."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = Path(os.environ.get("UMUSE_DATA_DIR", ROOT)).expanduser().resolve()
RAW = DATA_ROOT / "raw"
RESULTS = DATA_ROOT / "results"
