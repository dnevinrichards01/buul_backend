#!/bin/bash
set -e

until pg_isready -h db -p 5432; do
  echo "Waiting for database..."
  sleep 1
done
echo "Database is ready!"

if redis-cli -h redis -p 6379 ping | grep -q "PONG"; then
    echo "Redis is ready to accept connections."
else
    echo "Redis is not ready or unreachable."
fi

#doing this twice (once before in django app) causes errors
#python manage.py makemigrations
#python manage.py migrate 

exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf
#dexec tail -f /dev/null
#exec python manage.py runserver 0.0.0.0:8000
