"""
Config loader with environment variable override support.

Reads from config.py first, then environment variables with NSFC_ prefix take
precedence. Example: NSFC_CHROME_PATH overrides config.CHROME_PATH.
"""
import os


def _str(key, default):
    env = os.environ.get(f"NSFC_{key.upper()}")
    if env is not None:
        return env
    try:
        import config
        return getattr(config, key, default)
    except ImportError:
        print("WARNING: config.py not found. Run: cp templates/config-example.py config.py")
        return default


def _int(key, default):
    val = _str(key, None)
    if val is not None:
        return int(val)
    return default


def _float(key, default):
    val = _str(key, None)
    if val is not None:
        return float(val)
    return default


def _list(key, default):
    val = _str(key, None)
    if val is None:
        return default
    if isinstance(val, list):
        return val
    return [v.strip() for v in val.split(",") if v.strip()]


# Public API — use these instead of importing config directly
KEYWORDS = _list("KEYWORDS", [])
SUB_KEYWORDS = _list("SUB_KEYWORDS", [])
MATERIAL_KEYWORDS = _list("MATERIAL_KEYWORDS", [])
COLD_KEYWORDS = _list("COLD_KEYWORDS", [])
RERUN_KEYWORDS = _list("RERUN_KEYWORDS", [])
DOWNLOAD_DIR = _str("DOWNLOAD_DIR", os.path.join(os.path.expanduser("~"), "nsfc-reports"))
CHROME_PATH = _str("CHROME_PATH", None)
CDP_PORT = _int("CDP_PORT", 9222)
NSFC_HOST = _str("NSFC_HOST", "https://kd.nsfc.cn")
REQUEST_DELAY = _float("REQUEST_DELAY", 3.0)
IMAGE_TIMEOUT = _int("IMAGE_TIMEOUT", 30)
PAGE_TIMEOUT = _int("PAGE_TIMEOUT", 60)
MAX_RESULTS_THRESHOLD = _int("MAX_RESULTS_THRESHOLD", 90)
RESULTS_PER_PAGE = _int("RESULTS_PER_PAGE", 10)
MAX_PAGES_PER_SEARCH = _int("MAX_PAGES_PER_SEARCH", 10)
