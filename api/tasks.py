from celery import shared_task
import time

@shared_task(name="test_celery_task")
def test_celery_task():
    return True
    # we'll call a method in services which implements the logic. 
    # we'll call it in a celery task, and also in a view for future
    # view is last priority, may not even use at all unless for front end 