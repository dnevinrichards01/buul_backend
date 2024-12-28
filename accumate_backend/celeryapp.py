import os
from celery import Celery
from kombu import Queue
from .settings import REDIS_URL

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "accumate_backend.settings")
app = Celery("accumate_backend")
app.autodiscover_tasks()

# Redis broker URL with `rediss://` for TLS
app.conf.broker_url = 'rediss://:your_redis_password@your_redis_host:6379/0'

# TLS options
app.conf.broker_transport_options = {
    'ssl_cert_reqs': 'CERT_REQUIRED',  # Enforce server certificate validation
    'ssl_ca_certs': '/path/to/ca-cert.pem',  # Path to your CA cert file
}
app.conf.broker_url = 'rediss://' + REDIS_URL
app.conf.task_default_queue = 'default' # me
#app.conf.broker_connection_retry_on_startup = True #me
app.conf.result_backend = 'rediss://' + REDIS_URL
app.conf.accept_content = ["application/json"]
app.conf.task_serializer = "json"
app.conf.result_serializer = "json"
app.conf.task_default_queue = "main"
app.conf.task_create_missing_queues = True
app.conf.task_queues = (Queue("main"),)
app.conf.broker_pool_limit = 1
app.conf.broker_connection_timeout = 30
app.conf.worker_prefetch_multiplier = 1
app.conf.redbeat_redis_url = 'rediss://' + REDIS_URL