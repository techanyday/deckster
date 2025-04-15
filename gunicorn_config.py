import multiprocessing

# Gunicorn configuration
bind = "0.0.0.0:10000"
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "gevent"
timeout = 120
keepalive = 5
errorlog = "-"  # stderr
accesslog = "-"  # stdout
loglevel = "info"
capture_output = True
enable_stdio_inheritance = True
