#!/bin/bash
# The cronjobs and the scripts started from the web interface run as user nsm, the web
# interface itself as root (it writes /etc/cron.d/myjobs, which cron only accepts from root).
# Both write to /app/data: it belongs to group nsm with setgid, so files the web interface
# creates there get group nsm, and app.py's umask makes them writable for the jobs. This
# also fixes volumes from versions that ran everything as root.
find /app/data ! -name web-password.txt -exec chown nsm:nsm {} + -exec chmod g+rwX {} +
chmod g+s /app/data

# gunicorn instead of Flask's development server; one worker with threads, since some
# actions run the scripts synchronously and can take minutes
gunicorn --chdir /app --bind 0.0.0.0:5000 --workers 1 --threads 4 --access-logfile - app:app &
exec cron -f
