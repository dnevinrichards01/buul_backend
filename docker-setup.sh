#!/bin/bash
set -e

until nc -z db 5432; do
  echo "Waiting for database..."
  sleep 1
done
echo "Database is ready."

python manage.py makemigrations
python manage.py migrate 
exec python manage.py runserver 0.0.0.0:8000
