from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for, flash
import os
import json
from dotenv import load_dotenv
import logging
from datetime import datetime
from flask_wtf.csrf import CSRFProtect
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from flask_cors import CORS
import tempfile
import requests
from PIL import Image
from io import BytesIO
import openai
from flask_dance.contrib.google import make_google_blueprint, google
from flask_dance.consumer.storage.sqla import OAuthConsumerMixin, SQLAlchemyStorage
from flask_dance.consumer import oauth_authorized
from sqlalchemy.orm.exc import NoResultFound
from utils.utils import check_user_limits, get_max_slides, add_watermark, generate_presentation_content, create_ppt

# Load environment variables
load_dotenv()

# Initialize extensions
db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()

# Initialize Google Blueprint globally
google_bp = make_google_blueprint(
    client_id=os.getenv('GOOGLE_CLIENT_ID'),
    client_secret=os.getenv('GOOGLE_CLIENT_SECRET'),
    scope=['openid', 'https://www.googleapis.com/auth/userinfo.email', 'https://www.googleapis.com/auth/userinfo.profile'],
    redirect_url='/google/authorized'
)

# Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    name = db.Column(db.String(120))
    google_id = db.Column(db.String(256), unique=True)

    def get_id(self):
        return str(self.id)

class OAuth(OAuthConsumerMixin, db.Model):
    __tablename__ = "flask_dance_oauth"
    provider_user_id = db.Column(db.String(256), unique=True)
    user_id = db.Column(db.Integer, db.ForeignKey(User.id))
    user = db.relationship(User)

    def set_token(self, token):
        app.logger.debug(f"Token type: {type(token)}")
        app.logger.debug(f"Token content: {token}")
        
        # Convert token to dictionary if it's not already
        if not isinstance(token, dict):
            try:
                if hasattr(token, 'token'):
                    token = token.token
                token = {
                    'access_token': getattr(token, 'access_token', None),
                    'token_type': getattr(token, 'token_type', None),
                    'scope': getattr(token, 'scope', []),
                    'expires_in': getattr(token, 'expires_in', None),
                    'expires_at': getattr(token, 'expires_at', None),
                    'id_token': getattr(token, 'id_token', None)
                }
            except Exception as e:
                app.logger.error(f"Error converting token to dictionary: {str(e)}")
                token = {}
        
        app.logger.debug(f"Token after conversion: {token}")
        
        try:
            # Clean up the token dictionary
            token_dict = {
                'access_token': str(token.get('access_token', '')),
                'token_type': str(token.get('token_type', '')),
                'scope': token.get('scope', []),
                'expires_in': int(token.get('expires_in', 0)),
                'expires_at': float(token.get('expires_at', 0)),
                'id_token': str(token.get('id_token', ''))
            }
            
            # Convert scope to string if it's a list
            if isinstance(token_dict['scope'], list):
                token_dict['scope'] = ' '.join(token_dict['scope'])
            
            app.logger.debug(f"Final token_dict: {token_dict}")
            json_token = json.dumps(token_dict)
            app.logger.debug(f"JSON token: {json_token}")
            self.token = json_token
            
        except Exception as e:
            app.logger.error(f"Error in token serialization: {str(e)}")
            self.token = json.dumps({})

    def get_token(self):
        try:
            app.logger.debug(f"Stored token: {self.token}")
            token_dict = json.loads(self.token)
            app.logger.debug(f"Loaded token dict: {token_dict}")
            # Convert scope back to list if it was stored as a string
            if isinstance(token_dict.get('scope'), str):
                token_dict['scope'] = token_dict['scope'].split()
            return token_dict
        except json.JSONDecodeError as e:
            app.logger.error(f"Failed to decode token JSON: {str(e)}")
            return {}
        except Exception as e:
            app.logger.error(f"Unexpected error in get_token: {str(e)}")
            return {}

class Presentation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User', backref=db.backref('presentations', lazy=True))
    file_path = db.Column(db.String(500))
    status = db.Column(db.String(50), default='pending')
    error_message = db.Column(db.Text)

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///app.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['WTF_CSRF_ENABLED'] = True
    
    # Initialize extensions with app
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    
    # Register Google Blueprint
    app.register_blueprint(google_bp, url_prefix='/login')
    
    # Configure OAuth storage
    google_bp.storage = SQLAlchemyStorage(OAuth, db.session, user=current_user)
    
    return app

app = create_app()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.before_request
def before_request():
    if not request.is_secure and app.env != 'development':
        url = request.url.replace('http://', 'https://', 1)
        return redirect(url, code=301)

# Configure logging for production
if os.getenv('ENVIRONMENT') == 'production':
    logging.basicConfig(level=logging.INFO)
    gunicorn_logger = logging.getLogger('gunicorn.error')
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)
else:
    # Development logging
    logging.basicConfig(level=logging.DEBUG)
    app.logger.setLevel(logging.DEBUG)

# Get database URL - default to SQLite for local development
database_url = os.getenv('DATABASE_URL')
if database_url and database_url.startswith('postgres://'):
    # Render uses postgres://, but SQLAlchemy needs postgresql://
    database_url = database_url.replace('postgres://', 'postgresql://', 1)

app.config.update(
    SQLALCHEMY_DATABASE_URI=database_url or 'sqlite:///app.db',
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    SECRET_KEY=os.getenv('SECRET_KEY', 'dev-secret-key-123'),
    WTF_CSRF_ENABLED=True,
)

# Create database tables
with app.app_context():
    try:
        db.create_all()
        app.logger.info("Database tables created successfully")
    except Exception as e:
        app.logger.error(f"Error creating database tables: {str(e)}")

@oauth_authorized.connect_via(google_bp)
def google_logged_in(blueprint, token):
    try:
        app.logger.debug(f"OAuth callback received with token type: {type(token)}")
        if token is None:
            app.logger.error("Failed to get OAuth token")
            flash("Failed to log in with Google.", category="error")
            return False

        # Get user info from Google
        resp = blueprint.session.get('/oauth2/v2/userinfo')
        if not resp.ok:
            app.logger.error(f"Failed to get user info: {resp.text}")
            flash("Failed to get user info from Google.", category="error")
            return False

        google_info = resp.json()
        google_user_id = str(google_info['id'])
        
        # Find this OAuth token in the database, or create it
        query = OAuth.query.filter_by(
            provider=blueprint.name,
            provider_user_id=google_user_id,
        )
        try:
            oauth = query.first()
            if not oauth:
                oauth = OAuth(
                    provider=blueprint.name,
                    provider_user_id=google_user_id,
                    token=token,
                )
        except Exception as e:
            app.logger.error(f"Error querying OAuth: {str(e)}")
            flash("An error occurred during login.", category="error")
            return False

        if oauth.user:
            login_user(oauth.user)
            flash("Successfully signed in with Google.", category="success")
        else:
            # Create a new local user
            user = User(
                email=google_info['email'],
                name=google_info['name'],
                google_id=google_user_id,
            )
            oauth.user = user
            db.session.add_all([user, oauth])
            try:
                db.session.commit()
                login_user(user)
                flash("Successfully signed in with Google.", category="success")
            except Exception as e:
                app.logger.error(f"Error saving user: {str(e)}")
                db.session.rollback()
                flash("An error occurred during login.", category="error")
                return False

        return False  # Disable Flask-Dance's default behavior
        
    except Exception as e:
        app.logger.error(f"Unexpected error in google_logged_in: {str(e)}")
        flash("An unexpected error occurred during login.", category="error")
        return False

@app.after_request
def add_csrf_header(response):
    if response.mimetype == 'application/json':
        response.headers.set('X-CSRFToken', csrf.generate_csrf())
    return response

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/login')
def login():
    return redirect(url_for('google.login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    return jsonify({
        'status': 'error',
        'message': 'Registration is not available. Please use Google to sign in.'
    }), 400

@app.route('/verify-email/<token>')
def verify_email(token):
    return jsonify({
        'status': 'error',
        'message': 'Email verification is not available. Please use Google to sign in.'
    }), 400

@app.route('/resend-verification', methods=['POST'])
def resend_verification():
    return jsonify({
        'status': 'error',
        'message': 'Email verification is not available. Please use Google to sign in.'
    }), 400

@app.route('/generate', methods=['POST'])
@login_required
def generate():
    try:
        # Validate CSRF token
        csrf.protect()
        
        data = request.get_json()
        if not data or 'topic' not in data:
            return jsonify({'error': 'Missing topic in request'}), 400

        topic = data['topic']
        num_slides = data.get('num_slides', 5)  # Default to 5 slides if not specified

        # Check user limits
        max_slides = get_max_slides(current_user)
        if num_slides > max_slides:
            return jsonify({
                'error': f'Free accounts are limited to {max_slides} slides per presentation'
            }), 403

        if not check_user_limits(current_user):
            return jsonify({
                'error': 'You have reached your daily presentation limit'
            }), 403

        # Generate presentation content
        content = generate_presentation_content(topic, num_slides)
        
        # Create PowerPoint
        temp_ppt = tempfile.NamedTemporaryFile(suffix='.pptx', delete=False)
        create_ppt(content, temp_ppt.name)
        
        # Add watermark if needed
        if current_user.subscription_type == 'free':
            add_watermark(temp_ppt.name)

        # Save presentation to database
        presentation = Presentation(
            title=content[0]['title'] if content else "Untitled Presentation",
            file_path=temp_ppt.name,
            user=current_user,
            status='completed'
        )
        db.session.add(presentation)
        db.session.commit()

        return jsonify({
            'success': True,
            'presentation_id': presentation.id,
            'download_url': url_for('download_presentation', filename=presentation.file_path.split('/')[-1])
        })

    except Exception as e:
        app.logger.error(f"Error generating presentation: {str(e)}")
        return jsonify({'error': 'Failed to generate presentation'}), 500

@app.route('/pricing')
def pricing():
    return render_template('pricing.html', plans=['free', 'pro', 'business'])

@app.route('/subscribe', methods=['POST'])
@login_required
def subscribe():
    try:
        data = request.get_json()
        plan = data.get('plan')
        
        if not plan or plan not in ['free', 'pro', 'business']:
            return jsonify({
                'status': 'error',
                'message': 'Invalid subscription plan'
            }), 400
            
        if plan == 'free':
            current_user.subscription_type = 'free'
            db.session.commit()
            return jsonify({
                'status': 'success',
                'message': 'Successfully subscribed to Free plan'
            })
            
        # For paid plans, initialize payment with Paystack
        amount = {
            'pro': 1000,  # ₦1,000 per month
            'business': 5000  # ₦5,000 per month
        }.get(plan)
        
        url = "https://api.paystack.co/transaction/initialize"
        headers = {
            "Authorization": f"Bearer {app.config['PAYSTACK_SECRET_KEY']}",
            "Content-Type": "application/json"
        }
        data = {
            "email": current_user.email,
            "amount": amount * 100,  # Amount in kobo
            "callback_url": url_for('payment_callback', _external=True),
            "metadata": {
                "plan": plan,
                "user_id": current_user.id
            }
        }
        
        response = requests.post(url, headers=headers, json=data)
        if response.ok:
            data = response.json()
            if data.get('status'):
                return jsonify({
                    'status': 'success',
                    'authorization_url': data['data']['authorization_url']
                })
                
        return jsonify({
            'status': 'error',
            'message': 'Failed to initialize payment'
        }), 500
        
    except Exception as e:
        app.logger.error(f"Subscription error: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'An error occurred while processing your subscription'
        }), 500

@app.route('/payment/callback')
@login_required
def payment_callback():
    reference = request.args.get('reference')
    if not reference:
        flash('No reference provided')
        return redirect(url_for('pricing'))
        
    try:
        # Verify the transaction
        response = verify_paystack_transaction(reference)
        
        if response.get('status') and response['data']['status'] == 'success':
            metadata = response['data']['metadata']
            plan = metadata.get('plan')
            
            if plan in ['pro', 'business']:
                current_user.subscription_type = plan
                db.session.commit()
                flash(f'Successfully subscribed to {plan.title()} plan!')
            else:
                flash('Invalid subscription plan')
        else:
            flash('Payment verification failed')
            
    except Exception as e:
        app.logger.error(f"Payment callback error: {str(e)}")
        flash('An error occurred while processing your payment')
        
    return redirect(url_for('pricing'))

@app.route('/download/<filename>')
@login_required
def download_presentation(filename):
    try:
        # Get the presentation from the database
        presentation = Presentation.query.filter(
            Presentation.user_id == current_user.id,
            Presentation.file_path.like(f"%{filename}")
        ).first()
        
        if not presentation:
            return jsonify({
                'status': 'error',
                'message': 'Presentation not found'
            }), 404
            
        if not os.path.exists(presentation.file_path):
            return jsonify({
                'status': 'error',
                'message': 'Presentation file not found'
            }), 404
            
        return send_file(
            presentation.file_path,
            as_attachment=True,
            download_name='presentation.pptx'
        )
        
    except Exception as e:
        app.logger.error(f"Error downloading presentation: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'Failed to download presentation'
        }), 500

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    return jsonify({
        'status': 'error',
        'message': 'Password reset is not available. Please use Google to sign in.'
    }), 400

@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    return jsonify({
        'status': 'error',
        'message': 'Password reset is not available. Please use Google to sign in.'
    }), 400

if __name__ == '__main__':
    app.run(debug=True)
