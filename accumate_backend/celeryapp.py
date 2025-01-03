import os
from celery import Celery
from .settings import SQS_LONG_RUNNING_URL, SQS_USER_INTERACTION_URL, SQS_DLQ_URL

app = Celery(
    "accumate_backend",

)
app.autodiscover_tasks()

app = Celery(
    "app",
    broker_url="sqs://",
    broker_transport_options={
        "region": "us-west-1", # your AWS SQS region
        "predefined_queues": {
            "long-running": {  ## the name of the SQS queue
                "url": SQS_LONG_RUNNING_URL
            },
            "user-interaction": {
                "url": SQS_USER_INTERACTION_URL
            },
            "dlq": {
                "url": SQS_DLQ_URL
            }
        },
    },
    task_create_missing_queues=False,
)


app.conf.broker_connection_retry_on_startup = True
app.conf.task_default_queue = 'long-running'

#app.conf.result_backend = REDIS_URL
#app.conf.result_backend_transport_options = {
#    'key_prefix': '{celery}'
#}

app.conf.accept_content = ["application/json"] 
app.conf.task_serializer = "json"
app.conf.result_serializer = "json" 
app.conf.broker_pool_limit = 1
app.conf.broker_connection_timeout = 30
app.conf.worker_prefetch_multiplier = 1
#app.conf.redbeat_redis_url = REDIS_URL