#!/bin/bash
set -e

if redis-cli -h $REDIS_HOST -p $REDIS_PORT ping | grep -q "PONG"; then
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
