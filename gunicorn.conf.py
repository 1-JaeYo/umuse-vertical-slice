"""One process preserves the app's one-analysis-at-a-time lock and intake ordering."""
import os

bind = "0.0.0.0:" + os.environ.get("PORT", "8765")
workers = 1
worker_class = "gthread"
threads = 4
timeout = 900
graceful_timeout = 30
# Do not record participant codes in request URLs.
accesslog = None
errorlog = "-"
umask = 0o077
