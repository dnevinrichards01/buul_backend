#!/bin/bash
set -e

pip install -e /code/build_files/accumate_robinstocks

until pg_isready -h $DB_HOST -p $DB_PORT; do
  echo "Waiting for database..."
  sleep 1
done
echo "Database is ready!"

until redis-cli -h $REDIS_HOST -p $REDIS_PORT ping | grep -q "PONG"; do
    echo "Waiting for redis..."
    sleep 1
done
echo "Redis is ready!"

# python manage.py runserver 0.0.0.0:443 > logs.txt 2> logs_err.txt &
exec /usr/bin/supervisord -c /etc/supervisor/supervisord.conf
# exec tail -f /dev/null
