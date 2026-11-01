#!/usr/bin/env bash
# Render build script — runs during each deploy before the service starts.
set -o errexit

pip install -r requirements.txt

python manage.py collectstatic --no-input

python manage.py migrate
