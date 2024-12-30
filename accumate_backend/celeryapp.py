import os
from celery import Celery
from kombu import Queue
from .settings import REDIS_URL, REDIS_CAFILE_PATH


app = Celery("accumate_backend")
app.autodiscover_tasks()


app.conf.broker_url = REDIS_URL
app.conf.broker_transport_options = {
    'ssl_cert_reqs': 'CERT_REQUIRED',  # Enforce server certificate validation
    'ssl_ca_certs': REDIS_CAFILE_PATH,  # Path to your CA cert file
    'key_prefix': '{celery}'
}
app.conf.broker_connection_retry_on_startup = True
app.conf.task_default_queue = 'default' # me
#app.conf.broker_connection_retry_on_startup = True #me

app.conf.result_backend = REDIS_URL
app.conf.result_backend_transport_options = {
    'key_prefix': '{celery}'
}

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