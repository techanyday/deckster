#!/bin/bash

# Upgrade pip first
python -m pip install --upgrade pip

# Install gunicorn explicitly first
python -m pip install gunicorn

# Install all requirements
python -m pip install -r requirements.txt

# Verify gunicorn installation
which gunicorn
gunicorn --version
