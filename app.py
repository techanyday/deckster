from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for, flash
import os
from dotenv import load_dotenv
import logging
from utils.utils import check_user_limits, get_max_slides, add_watermark, generate_presentation_content, create_ppt
from flask_wtf.csrf import CSRFProtect
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from datetime import datetime
from flask_cors import CORS
import tempfile
import requests
from PIL import Image
from io import BytesIO
import openai
import json
from flask_dance.contrib.google import make_google_blueprint, google
from flask_dance.consumer.storage.sqla import OAuthConsumerMixin, SQLAlchemyStorage
from flask_dance.consumer import oauth_authorized
from sqlalchemy.orm.exc import NoResultFound

# Load environment variables
load_dotenv()

# Initialize Flask app and load config
app = Flask(__name__)

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

# Initialize extensions
db = SQLAlchemy(app)
csrf = CSRFProtect(app)

# Initialize login manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'google.login'

# Configure Google OAuth
google_bp = make_google_blueprint(
    client_id=os.getenv('GOOGLE_CLIENT_ID'),
    client_secret=os.getenv('GOOGLE_CLIENT_SECRET'),
    scope=['https://www.googleapis.com/auth/userinfo.email',
           'https://www.googleapis.com/auth/userinfo.profile',
           'openid'],
    redirect_to='index'
)
app.register_blueprint(google_bp, url_prefix='/login')

# Import models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    name = db.Column(db.String(120))
    subscription_type = db.Column(db.String(20), default='free')
    presentations = db.relationship('Presentation', backref='user', lazy=True)
    google_id = db.Column(db.String(256), unique=True)

    def get_id(self):
        return str(self.id)

    @property
    def is_active(self):
        return True

    @property
    def is_authenticated(self):
        return True

    @property
    def is_anonymous(self):
        return False

class OAuth(OAuthConsumerMixin, db.Model):
    user_id = db.Column(db.Integer, db.ForeignKey(User.id))
    user = db.relationship(User)

class Presentation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

# Create database tables
with app.app_context():
    try:
        db.create_all()
        app.logger.info("Database tables created successfully")
    except Exception as e:
        app.logger.error(f"Error creating database tables: {str(e)}")

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Set OpenAI API key
openai.api_key = os.getenv('OPENAI_API_KEY')

CORS(app)

# Configure OAuth storage
google_bp.storage = SQLAlchemyStorage(OAuth, db.session, user=current_user)

@oauth_authorized.connect_via(google_bp)
def google_logged_in(blueprint, token):
    app.logger.debug("OAuth callback started")
    try:
        if not token:
            app.logger.error("No token received from Google")
            flash("Failed to log in with Google.", category="error")
            return False

        try:
            app.logger.debug("Getting user info from Google")
            resp = blueprint.session.get("https://www.googleapis.com/oauth2/v2/userinfo")
            app.logger.debug(f"Google API response status: {resp.status_code}")
            app.logger.debug(f"Google API response headers: {resp.headers}")
            
            if not resp.ok:
                app.logger.error(f"Failed to get user info from Google: {resp.text}")
                flash("Failed to fetch user info from Google.", category="error")
                return False

            google_info = resp.json()
            app.logger.debug(f"Received user info from Google: {google_info}")
            
            if 'id' not in google_info:
                app.logger.error("No user ID in Google response")
                flash("Failed to get user ID from Google.", category="error")
                return False

            google_user_id = str(google_info["id"])
            app.logger.debug(f"Processing user with Google ID: {google_user_id}")

            # Find this OAuth token in the database, or create it
            query = OAuth.query.filter_by(
                provider=blueprint.name,
                provider_user_id=google_user_id,
            )
            try:
                oauth = query.one()
                app.logger.debug("Found existing OAuth token")
            except NoResultFound:
                app.logger.debug("Creating new OAuth token")
                oauth = OAuth(
                    provider=blueprint.name,
                    provider_user_id=google_user_id,
                    token=token,
                )

            if oauth.user:
                app.logger.debug("Logging in existing user")
                login_user(oauth.user)
                flash("Successfully signed in with Google.")
            else:
                app.logger.debug("Creating new user")
                # Create a new local user account for this user
                user = User(
                    email=google_info.get("email", ""),
                    name=google_info.get("name", ""),
                    google_id=google_user_id,
                )
                # Associate the new local user account with the OAuth token
                oauth.user = user
                # Save and commit our database models
                db.session.add_all([user, oauth])
                db.session.commit()
                app.logger.debug("New user created and saved")
                # Log in the new local user account
                login_user(user)
                flash("Successfully signed in with Google.")

            app.logger.debug("OAuth callback completed successfully")
            return False

        except Exception as e:
            app.logger.error(f"Error in Google API request: {str(e)}", exc_info=True)
            flash("An error occurred during Google sign-in. Please try again.", category="error")
            return False

    except Exception as e:
        app.logger.error(f"Error in OAuth callback: {str(e)}", exc_info=True)
        flash("An error occurred during Google sign-in. Please try again.", category="error")
        return False

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
        if not check_user_limits(current_user):
            return jsonify({
                'status': 'error',
                'message': 'You have reached your presentation limit. Please upgrade your plan.'
            }), 400

        # Get form data
        mode = request.form.get('mode')
        input_text = request.form.get('input')
        template = request.form.get('template', 'modern')
        
        if not mode or not input_text:
            return jsonify({
                'status': 'error',
                'message': 'Mode and input text are required'
            }), 400
            
        # Generate presentation content
        content = generate_presentation_content(input_text, mode)
        if not content:
            return jsonify({
                'status': 'error',
                'message': 'Failed to generate presentation content'
            }), 500
            
        try:
            # Parse content as JSON
            slides = json.loads(content)
            
            # Create PowerPoint
            temp_ppt = create_ppt(slides, template)
            if not temp_ppt:
                return jsonify({
                    'status': 'error',
                    'message': 'Failed to create PowerPoint file'
                }), 500
            
            # Save presentation to database
            presentation = Presentation(
                title=slides[0]['title'] if slides else "Untitled Presentation",
                content=content,
                file_path=temp_ppt.name,
                user=current_user
            )
            db.session.add(presentation)
            db.session.commit()
            
            return jsonify({
                'status': 'success',
                'content': content,
                'filename': os.path.basename(temp_ppt.name)
            })
            
        except Exception as e:
            app.logger.error(f"Error creating presentation file: {str(e)}")
            return jsonify({
                'status': 'error',
                'message': 'Failed to create presentation file'
            }), 500
            
    except Exception as e:
        app.logger.error(f"Error generating presentation: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'An error occurred while generating the presentation'
        }), 500

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
