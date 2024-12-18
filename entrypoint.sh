#!/bin/bash
set -e

until pg_isready -h db -p 5432; do
  echo "Waiting for database..."
  sleep 1
done
echo "Database is ready!"

python manage.py makemigrations
python manage.py migrate 
#exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf
exec tail -f /dev/null
#exec python manage.py runserver 0.0.0.0:8000
