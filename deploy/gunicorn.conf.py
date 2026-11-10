import multiprocessing
import os

bind = os.getenv("BIND", "127.0.0.1:8000")
workers = int(os.getenv("WEB_WORKERS", str(max(2, multiprocessing.cpu_count()))))
timeout = 60
graceful_timeout = 30
accesslog = "-"
errorlog = "-"
