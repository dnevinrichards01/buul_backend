from django.apps import AppConfig, apps
from django.db.utils import ProgrammingError, OperationalError

class ApiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'api'

    def ready(self):
        from api import views, models
        # from api.tasks import investTasks, userTasks
        PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
        CrontabSchedule = apps.get_model("django_celery_beat", "CrontabSchedule")

        task_name = "refresh_stock_data"

        try:
            # Check if the task already exists, and create it if it doesn't
            task, created = PeriodicTask.objects.get_or_create(
                crontab = CrontabSchedule.objects.get_or_create(
                        minute=0,
                        hour=0,
                        day_of_week="*",
                        day_of_month="*",
                        month_of_year='*'
                    )[0],
                name = task_name,
                defaults={
                    "task": f"api.tasks.investTasks.{task_name}",
                },
            )
            if created:
                print(f"Periodic task '{task_name}' created.")
            else:
                print(f"Periodic task '{task_name}' already exists.")
        except (ProgrammingError, OperationalError):
            # These errors occur during migrations or if the database is not ready
            print(f"Skipping task creation for '{task_name}' due to database readiness issues.")