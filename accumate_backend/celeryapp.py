import os
from celery import Celery
from kombu import Queue
from .settings import REDIS_URL

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "accumate_backend.settings")
app = Celery("accumate_backend")
app.autodiscover_tasks()
app.conf.broker_url = REDIS_URL
app.conf.result_backend = REDIS_URL
app.conf.accept_content = ["application/json"]
app.conf.task_serializer = "json"
app.conf.result_serializer = "json"
app.conf.task_default_queue = "main"
app.conf.task_create_missing_queues = True
app.conf.task_queues = (Queue("main"),)
app.conf.broker_pool_limit = 1
app.conf.broker_connection_timeout = 30
app.conf.worker_prefetch_multiplier = 1
app.conf.redbeat_redis_url = REDIS_URL