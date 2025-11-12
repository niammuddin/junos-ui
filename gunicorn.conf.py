import multiprocessing
import os


def _int_env(name: str, default: int) -> int:
    """Read integer values from the environment with a fallback."""
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


bind = os.environ.get("GUNICORN_BIND", f"0.0.0.0:{os.environ.get('PORT', 5000)}")
workers = _int_env("GUNICORN_WORKERS", multiprocessing.cpu_count() * 2 + 1)
worker_class = os.environ.get("GUNICORN_WORKER_CLASS", "sync")
timeout = _int_env("GUNICORN_TIMEOUT", 90)
graceful_timeout = _int_env("GUNICORN_GRACEFUL_TIMEOUT", 30)
keepalive = _int_env("GUNICORN_KEEPALIVE", 5)
max_requests = _int_env("GUNICORN_MAX_REQUESTS", 1000)
max_requests_jitter = _int_env("GUNICORN_MAX_REQUESTS_JITTER", 50)
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")
accesslog = os.environ.get("GUNICORN_ACCESSLOG", "-")
errorlog = os.environ.get("GUNICORN_ERRORLOG", "-")
capture_output = True
preload_app = False
