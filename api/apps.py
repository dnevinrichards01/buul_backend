from django.apps import AppConfig, apps
from django.db.utils import ProgrammingError, OperationalError
import json

class ApiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'api'

    def ready(self):
        from api import views, models
        PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
        CrontabSchedule = apps.get_model("django_celery_beat", "CrontabSchedule")

        try:
            curr_task_name = "first task"

            crontab_minutely, _ = CrontabSchedule.objects.get_or_create(
                minute="*",
                hour="*",
                day_of_week="*",
                day_of_month="*",
                month_of_year="*"
            )
            crontab_daily, _ = CrontabSchedule.objects.get_or_create(
                minute=0,
                hour=0,
                day_of_week="*",
                day_of_month="*",
                month_of_year="*"
            )
            crontab_weekly, _ = CrontabSchedule.objects.get_or_create(
                minute=0,
                hour=0,
                day_of_week=1,
                day_of_month="*",
                month_of_year="*"
            )

            tasks = {
                "refresh_stock_data_by_interval": {
                    "kwargs": json.dumps({"interval": "1m"}),
                    "crontab": crontab_minutely,
                    "task_type": "graphTasks"
                },
                "delete_non_closing_times": {
                    "kwargs": json.dumps({}),
                    "crontab": crontab_daily,
                    "task_type": "graphTasks"
                },
                "plaid_access_token_refresh_all": {
                    "kwargs": json.dumps({}),
                    "crontab": crontab_daily,
                    "task_type": "userTasks"
                }
                # "all_users_spending_by_category": {
                #     "kwargs": json.dumps({}),
                #     "crontab": crontab_weekly,
                #     "task_type": "transactionsTasks"
                # }
                
            }

            for task_name in tasks:
                curr_task_name = task_name
                # Check if the task already exists, and create it if it doesn't
                task, created = PeriodicTask.objects.get_or_create(
                    crontab = tasks[task_name]["crontab"],
                    name = task_name,
                    defaults={
                        "task": task_name,#f"api.tasks.{tasks[task_name]["task_type"]}.{task_name}",
                        "kwargs": tasks[task_name]["kwargs"]
                    },
                )
                if created:
                    print(f"Periodic task '{task_name}' created.")
                else:
                    print(f"Periodic task '{task_name}' already exists.")
        except (ProgrammingError, OperationalError):
            # These errors occur during migrations or if the database is not ready
            print(f"Skipping task creation for '{curr_task_name}' due to database readiness issues.")

