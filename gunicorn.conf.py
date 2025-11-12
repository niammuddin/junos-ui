import multiprocessing
import os


def _int_env(name: str, default: int) -> int:
    """Read integer values from the environment with a fallback."""
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


bind = os.environ.get("GUNICORN_BIND", f"0.0.0.0:{os.environ.get('PORT', 5000)}")
# gNMI monitoring keeps state in-process, so default to a single worker unless explicitly overridden.
workers = _int_env("GUNICORN_WORKERS", 1)
threads = _int_env("GUNICORN_THREADS", max(4, multiprocessing.cpu_count()))
worker_class = os.environ.get("GUNICORN_WORKER_CLASS", "gthread" if threads > 1 else "sync")
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
