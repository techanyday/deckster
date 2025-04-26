#!/bin/bash

# Install dependencies
pip install -r requirements.txt

# Install gunicorn explicitly
pip install gunicorn

# Start the application
exec gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 2 --timeout 120
