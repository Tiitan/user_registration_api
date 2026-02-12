#!/bin/sh
set -eu

python -m scripts.registration_cleanup
exec supercronic -no-reap /app/scripts/cron/registration_cleanup.cron
