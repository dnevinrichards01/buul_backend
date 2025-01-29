import os
from celery import Celery
from .settings import SQS_LONG_RUNNING_URL, SQS_USER_INTERACTION_URL, SQS_DLQ_URL, SQS_CONTROL_URL
import django
from kombu import Queue

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'accumate_backend.settings')
# django.setup()

app = Celery(
    "accumate_backend",
)


# autodiscover tasks in installed apps
#django.setup() # imports those installed apps
# app.autodiscover_tasks(['api', 'robin_stocks'], force=True)
app.conf.imports = [
    "api.tasks.userTasks",
    "api.tasks.investTasks",
    "api.tasks.depositTasks",
    "api.tasks.transactionsTasks",
    "robin_stocks.tasks",
]

# Explicitly disable dynamic reply queues, won't be able to use inspect command
#app.conf.worker_direct = False

app = Celery(
    "app",
    broker_url="sqs://",
    broker_transport_options={
        "region": "us-west-1", # your AWS SQS region
        "predefined_queues": {
            "ab-long-running": {  ## the name of the SQS queue
                "url": SQS_LONG_RUNNING_URL
            },
            "ab-user-interaction": {
                "url": SQS_USER_INTERACTION_URL
            },
            "ab-dlq": {
                "url": SQS_DLQ_URL
            }
        },
    },
    task_create_missing_queues=True,
)


app.conf.broker_connection_retry_on_startup = True
app.conf.task_default_queue = 'ab-long-running'
app.conf.result_backend = 'django-db'
app.conf.result_extended = True
app.conf.accept_content = ["application/json"] 
app.conf.task_serializer = "json"
app.conf.result_serializer = "json" 
app.conf.broker_pool_limit = 1
app.conf.broker_connection_timeout = 30
app.conf.worker_prefetch_multiplier = 1
#app.conf.redbeat_redis_url = REDIS_URL

#app.conf.control_queue = 'ab-control'
