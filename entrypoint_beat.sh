#!/bin/bash
set -e

#--tls 
until redis-cli -h $REDIS_HOST -p $REDIS_PORT ping | grep -q "PONG"; do
    echo "Waiting for redis..."
    sleep 1
done
echo "Redis is ready!"

#doing this twice (once before in django app) causes errors
#python manage.py makemigrations
#python manage.py migrate 

exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf
#exec tail -f /dev/null
#exec python manage.py runserver 0.0.0.0:8000
