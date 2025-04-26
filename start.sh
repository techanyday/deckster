#!/bin/bash

# Install dependencies
pip install -r requirements.txt

# Install gunicorn explicitly
pip install gunicorn

# Find the Python executable
PYTHON_PATH=$(which python3 || which python)

# Find gunicorn in the same directory as Python
GUNICORN_PATH=$(dirname $PYTHON_PATH)/gunicorn

# Start the application using the full path to gunicorn
exec $GUNICORN_PATH app:app --bind 0.0.0.0:$PORT --workers 1 --threads 2 --timeout 180
