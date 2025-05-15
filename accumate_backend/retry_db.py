import boto3
import json
from botocore.exceptions import ClientError
from django.db import connections
from django.conf import settings
from .settings import ENVIRONMENT
import threading
import functools
import psycopg2
from django.db.utils import OperationalError
# from psycopg2 import OperationalError
from rest_framework.views import exception_handler

def get_secret(secret_name, region_name="us-west-1"):
    client = boto3.client("secretsmanager", region_name=region_name)
    try:
        response = client.get_secret_value(SecretId=secret_name)
    except ClientError as e:
        raise Exception(f"Failed to retrieve secret: {e}")
    if "SecretString" in response:
        secret = response["SecretString"]
        try:
            return json.loads(secret)
        except json.JSONDecodeError:
            return secret
    else:
        raise Exception("Secret binary not supported in this function.")

def refresh_db_credentials(new_creds, alias="default"):
    db_settings = settings.DATABASES[alias]
    db_settings.update({
        "USER": new_creds["username"],
        "PASSWORD": new_creds["password"]
    })

    # Force-close the current DB connection (per-thread)
    conn = connections[alias]
    conn.close_if_unusable_or_obsolete()
    conn.close()

    # Also clear the thread-local connection wrapper so Django re-inits it
    if hasattr(threading.local(), 'connections'):
        del threading.local().connections


def retry_on_db_error(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except OperationalError as e:
            if "password authentication failed" in str(e):
                secret = get_secret(f"ecs/{ENVIRONMENT}/DB_CREDENTIALS")
                refresh_db_credentials(secret)
                return func(*args, **kwargs)
            raise
    return wrapper


def custom_exception_handler(exc, context):
    if isinstance(exc, OperationalError) and "password authentication failed" in str(exc):
        secret = get_secret(f"ecs/{ENVIRONMENT}/DB_CREDENTIALS")
        refresh_db_credentials(secret)
        # Retry manually here — might require calling the view again
        # or returning a special response
        # WARNING: this is tricky to retry safely here
    return exception_handler(exc, context)