#!/bin/bash
set -e

until pg_isready -h $DB_HOST -p $DB_PORT; do
  echo "Waiting for database..."
  sleep 1
done
echo "Database is ready!"

show_migrations=$(eval "python manage.py showmigrations")
if show_migrations | grep -q "[ ]"; then
    echo "migrations already made"
else
    echo "making migrations"
    python manage.py makemigrations
    python manage.py migrate