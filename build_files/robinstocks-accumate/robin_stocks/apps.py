from django.apps import AppConfig, apps
import json
from django.db.utils import ProgrammingError, OperationalError

class MyLibraryConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "robin_stocks"
    
    # def ready(self):
    #     import robin_stocks.signals 

    def ready(self):
        from django.apps import apps
        from robin_stocks import serializers, views, tasks, models
        # from robin_stocks.robinhood import authentication, helper


        # Import models dynamically to avoid "app not registered" errors
        PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
        IntervalSchedule = apps.get_model("django_celery_beat", "IntervalSchedule")

        task_name = "refresh_robinhood"

        try:
            # Check if the task already exists, and create it if it doesn't
            task, created = PeriodicTask.objects.get_or_create(
                name=task_name,
                defaults={
                    "interval": IntervalSchedule.objects.get_or_create(
                        every=1, period=IntervalSchedule.DAYS
                    )[0],
                    "task": f"robin_stocks.tasks.{task_name}"
                },
            )
            if created:
                print(f"Periodic task '{task_name}' created.")
            else:
                print(f"Periodic task '{task_name}' already exists.")
        except (ProgrammingError, OperationalError):
            # These errors occur during migrations or if the database is not ready
            print(f"Skipping task creation for '{task_name}' due to database readiness issues.")
