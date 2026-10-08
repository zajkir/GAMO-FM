"""Production Gunicorn defaults for GAMO Facility Platform.

Render sets WEB_CONCURRENCY from the available CPU allocation. Threads provide
I/O concurrency for PostgreSQL and polling endpoints without multiplying the
application/migration startup cost.
"""
import os

workers = max(1, int(os.environ.get("WEB_CONCURRENCY", "1")))
worker_class = "gthread"
threads = max(2, min(8, int(os.environ.get("GAMO_GUNICORN_THREADS", "4"))))
timeout = max(30, int(os.environ.get("GAMO_GUNICORN_TIMEOUT", "60")))
graceful_timeout = 30
keepalive = 5
max_requests = 2000
max_requests_jitter = 250
preload_app = False
accesslog = "-"
errorlog = "-"
capture_output = True
