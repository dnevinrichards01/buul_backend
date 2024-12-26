#!/bin/bash
set -e

until pg_isready -h $DB_HOST -p $DB_PORT; do
  echo "Waiting for database..."
  sleep 1
done
echo "Database is ready!"

until redis-cli -h $REDIS_HOST -p $REDIS_PORT --tls ping | grep -q "PONG"; do
    echo "Waiting for redis..."
    sleep 1
done
echo "Redis is ready!"

#doing this twice (once before in django app) causes errors
#python manage.py makemigrations
#python manage.py migrate 

exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf
#dexec tail -f /dev/null
#exec python manage.py runserver 0.0.0.0:8000
