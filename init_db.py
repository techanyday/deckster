import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

# Create Flask app
app = Flask(__name__)

# Configure database
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'dev-secret-key-123'

# Initialize database
db = SQLAlchemy(app)

# Import models
from models import User, Presentation

# Create tables
with app.app_context():
    db.create_all()
    print("Database tables created successfully!")
