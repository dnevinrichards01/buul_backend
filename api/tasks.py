from celery import shared_task
import time


@shared_task(name="test_celery_task")
def test_celery_task():
    time.sleep(5)
    return True

