from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    name = db.Column(db.String(100))
    subscription_type = db.Column(db.String(20), default='free')  # free, pro, business
    paystack_customer_code = db.Column(db.String(100), unique=True)
    subscription_reference = db.Column(db.String(100), unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    presentations = db.relationship('Presentation', backref='user', lazy=True)

class Presentation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200))
    content = db.Column(db.Text)
    slides_count = db.Column(db.Integer)
    file_path = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class SubscriptionPlan:
    PLANS = {
        'free': {
            'name': 'Starter',
            'price': 0,
            'currency': 'USD',
            'max_slides': 3,
            'presentations_limit': 3,  # per week
            'features': ['Basic themes', 'PPTX download', 'Watermark']
        },
        'pro': {
            'name': 'Creator',
            'price': 999,  # $9.99 (in cents)
            'currency': 'USD',
            'max_slides': 10,
            'presentations_limit': 20,  # per month
            'features': ['Premium themes', 'No watermark', 'PPTX + PDF export', 'Priority support']
        },
        'business': {
            'name': 'Professional',
            'price': 2499,  # $24.99 (in cents)
            'currency': 'USD',
            'max_slides': 30,
            'presentations_limit': 50,  # per month
            'features': ['Custom branding', 'Team sharing', 'Analytics dashboard', 'All Pro features']
        }
    }
