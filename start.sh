#!/bin/bash

# Create and activate a virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Verify gunicorn installation
python -m pip install gunicorn
which gunicorn
gunicorn --version

# Start the application
exec gunicorn app:app --bind 0.0.0.0:$PORT --timeout 180
