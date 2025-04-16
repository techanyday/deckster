from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for, flash
import os
from dotenv import load_dotenv
import logging
from utils import check_user_limits, get_max_slides, add_watermark, generate_presentation_content, create_ppt
from flask_wtf.csrf import CSRFProtect
from itsdangerous import URLSafeTimedSerializer
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from flask_cors import CORS
import tempfile
import requests
from PIL import Image
from io import BytesIO
import openai

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
    MAIL_SERVER=os.getenv('MAIL_SERVER', 'smtp.gmail.com'),
    MAIL_PORT=int(os.getenv('MAIL_PORT', '587')),
    MAIL_USE_TLS=os.getenv('MAIL_USE_TLS', 'True').lower() == 'true',
    MAIL_USERNAME=os.getenv('MAIL_USERNAME'),
    MAIL_PASSWORD=os.getenv('MAIL_PASSWORD'),
    MAIL_DEFAULT_SENDER=os.getenv('MAIL_DEFAULT_SENDER')
)

# Initialize extensions
db = SQLAlchemy(app)
csrf = CSRFProtect(app)
ts = URLSafeTimedSerializer(app.config["SECRET_KEY"])

# Initialize login manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Import models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    subscription_type = db.Column(db.String(20), default='free')
    presentations = db.relationship('Presentation', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

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

def verify_paystack_transaction(reference):
    """Verify Paystack transaction."""
    url = f"https://api.paystack.co/transaction/verify/{reference}"
    headers = {
        "Authorization": f"Bearer {app.config['PAYSTACK_SECRET_KEY']}",
        "Content-Type": "application/json"
    }
    response = requests.get(url, headers=headers)
    return response.json()

def generate_image(prompt):
    """Generate an image using DALL-E 3."""
    try:
        # Generate image with DALL-E 3
        response = openai.Image.create(
            model="dall-e-3",
            prompt=f"Create a professional, presentation-style image for: {prompt}. Make it suitable for a business presentation, with clean and modern aesthetics.",
            n=1,
            size="1792x1024",
            quality="standard"
        )
        
        # Get the image URL
        image_url = response.data[0].url
        
        # Download the image
        image_response = requests.get(image_url)
        image_response.raise_for_status()
        
        # Open and process the image
        image = Image.open(BytesIO(image_response.content))
        
        # Create a temporary file for the image
        temp_image = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
        image.save(temp_image.name, 'PNG')
        
        return temp_image.name
    except Exception as e:
        app.logger.error(f"Error generating image: {str(e)}")
        return None

def extract_image_prompt(content):
    """Extract a relevant image prompt from slide content."""
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are an expert at creating image generation prompts. Create a clear, specific prompt that will generate a relevant image for a presentation slide. Focus on visual elements and keep the prompt concise."},
                {"role": "user", "content": f"Create an image generation prompt for this slide content: {content}"}
            ],
            temperature=0.7
        )
        return response.choices[0].message['content'].strip()
    except Exception as e:
        app.logger.error(f"Error creating image prompt: {str(e)}")
        return None

def extract_slide_keywords(content):
    """Extract relevant keywords from slide content for image search."""
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are an expert at extracting relevant image search keywords from presentation content. Return only the keywords, no other text."},
                {"role": "user", "content": f"Extract 1-2 most relevant keywords for an image search from this slide content, focusing on concrete visual concepts: {content}"}
            ],
            temperature=0.3
        )
        return response.choices[0].message['content'].strip()
    except Exception as e:
        app.logger.error(f"Error extracting keywords: {str(e)}")
        return None

def send_password_reset_email(user_email, reset_url):
    """Send password reset email to user."""
    try:
        msg = MIMEMultipart()
        msg['Subject'] = 'Password Reset Request'
        msg['From'] = app.config['MAIL_DEFAULT_SENDER']
        msg['To'] = user_email

        html = f"""
        <h3>Password Reset Request</h3>
        <p>To reset your password, please click the link below:</p>
        <p><a href="{reset_url}">Reset Password</a></p>
        <p>If you did not request a password reset, please ignore this email.</p>
        <p>This link will expire in 1 hour.</p>
        """

        msg.attach(MIMEText(html, 'html'))

        with smtplib.SMTP(app.config['MAIL_SERVER'], app.config['MAIL_PORT']) as server:
            if app.config['MAIL_USE_TLS']:
                server.starttls()
            if app.config['MAIL_USERNAME'] and app.config['MAIL_PASSWORD']:
                server.login(app.config['MAIL_USERNAME'], app.config['MAIL_PASSWORD'])
            server.send_message(msg)
            
        return True
    except Exception as e:
        app.logger.error(f"Error sending password reset email: {str(e)}")
        return False

@app.route('/')
@login_required
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        try:
            data = request.get_json()
            if not data:
                return jsonify({'status': 'error', 'message': 'No data provided'}), 400
            
            email = data.get('email')
            password = data.get('password')
            
            if not email or not password:
                return jsonify({'status': 'error', 'message': 'Email and password are required'}), 400

            user = User.query.filter_by(email=email).first()
            if user and user.check_password(password):
                login_user(user)
                return jsonify({'status': 'success'})
            
            return jsonify({'status': 'error', 'message': 'Invalid email or password'}), 401
        except Exception as e:
            app.logger.error(f"Login error: {str(e)}")
            return jsonify({'status': 'error', 'message': 'An error occurred during login'}), 500
    
    # GET request - render the login template
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            data = request.get_json()
            if not data:
                return jsonify({'status': 'error', 'message': 'No data provided'}), 400
            
            email = data.get('email')
            name = data.get('name')
            password = data.get('password')
            
            if not email or not name or not password:
                return jsonify({'status': 'error', 'message': 'All fields are required'}), 400
                
            if User.query.filter_by(email=email).first():
                return jsonify({'status': 'error', 'message': 'Email already registered'}), 400
            
            try:
                user = User(
                    email=email,
                    name=name
                )
                user.set_password(password)
                db.session.add(user)
                db.session.commit()
                login_user(user)
                return jsonify({'status': 'success'})
            except Exception as e:
                db.session.rollback()
                app.logger.error(f"Database error during registration: {str(e)}")
                return jsonify({'status': 'error', 'message': 'Error creating user account'}), 500
                
        except Exception as e:
            app.logger.error(f"Registration error: {str(e)}")
            return jsonify({'status': 'error', 'message': 'An error occurred during registration'}), 500
            
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

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
                'message': 'Missing required fields'
            }), 400

        # Get custom styles
        custom_styles = {
            'title': request.form.get('titleColor', '#000000'),
            'text': request.form.get('textColor', '#000000'),
            'background': {}
        }

        background_style = request.form.get('backgroundStyle', 'solid')
        if background_style == 'solid':
            custom_styles['background'] = {
                'type': 'solid',
                'color': request.form.get('backgroundColor', '#FFFFFF')
            }
        elif background_style == 'gradient':
            custom_styles['background'] = {
                'type': 'gradient',
                'color1': request.form.get('gradientStart', '#FFFFFF'),
                'color2': request.form.get('gradientEnd', '#E0E0E0')
            }
        elif background_style == 'pattern':
            custom_styles['background'] = {
                'type': 'pattern',
                'color1': request.form.get('patternColor1', '#FFFFFF'),
                'color2': request.form.get('patternColor2', '#E0E0E0')
            }

        # Generate presentation content
        content = generate_presentation_content(mode, input_text)
        if not content:
            return jsonify({
                'status': 'error',
                'message': 'Failed to generate presentation content'
            }), 500

        try:
            # Create temporary file for the presentation
            temp_ppt = tempfile.NamedTemporaryFile(delete=False, suffix='.pptx')
            
            # Create the presentation with custom styles
            create_ppt(content, temp_ppt.name, template, custom_styles)
            
            # Add watermark if user is on free plan
            if current_user.subscription_type == 'free':
                add_watermark(temp_ppt.name)
            
            # Save presentation record
            presentation = Presentation(
                title=f"Presentation {datetime.utcnow()}",
                content=content,
                file_path=temp_ppt.name,
                user_id=current_user.id
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
            
        # Get amount based on plan
        amounts = {
            'pro': 2000,  # $20 in cents
            'business': 5000  # $50 in cents
        }
        
        amount = amounts.get(plan)
        if not amount:
            return jsonify({
                'status': 'error',
                'message': 'Invalid plan selected'
            }), 400
            
        # Initialize transaction with Paystack
        url = "https://api.paystack.co/transaction/initialize"
        headers = {
            "Authorization": f"Bearer {os.getenv('PAYSTACK_SECRET_KEY')}",
            "Content-Type": "application/json"
        }
        
        callback_url = url_for('payment_callback', _external=True)
        
        payload = {
            "email": current_user.email,
            "amount": amount,
            "callback_url": callback_url,
            "metadata": {
                "user_id": current_user.id,
                "plan": plan
            }
        }
        
        response = requests.post(url, json=payload, headers=headers)
        
        if response.status_code == 200:
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
        presentation = Presentation.query.filter_by(
            user_id=current_user.id,
            file_path__contains=filename
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
    if request.method == 'POST':
        try:
            data = request.get_json()
            if not data or not data.get('email'):
                return jsonify({'status': 'error', 'message': 'Email is required'}), 400
            
            email = data.get('email')
            user = User.query.filter_by(email=email).first()
            
            if not user:
                # Don't reveal that the user doesn't exist
                return jsonify({'status': 'success', 'message': 'If your email exists in our system, you will receive a password reset link shortly.'}), 200
            
            # Generate token
            token = ts.dumps(user.email, salt='password-reset-salt')
            
            # Build reset URL
            reset_url = url_for('reset_password', token=token, _external=True)
            
            # Send email
            if send_password_reset_email(user.email, reset_url):
                return jsonify({'status': 'success', 'message': 'If your email exists in our system, you will receive a password reset link shortly.'}), 200
            else:
                return jsonify({'status': 'error', 'message': 'Failed to send reset email. Please try again later.'}), 500
                
        except Exception as e:
            app.logger.error(f"Password reset request error: {str(e)}")
            return jsonify({'status': 'error', 'message': 'An error occurred. Please try again later.'}), 500
            
    return render_template('forgot_password.html')

@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    try:
        email = ts.loads(token, salt='password-reset-salt', max_age=3600)  # Token expires in 1 hour
    except:
        return render_template('reset_password.html', error='Invalid or expired reset link. Please try again.')
    
    if request.method == 'POST':
        try:
            data = request.get_json()
            if not data or not data.get('password'):
                return jsonify({'status': 'error', 'message': 'New password is required'}), 400
            
            user = User.query.filter_by(email=email).first()
            if not user:
                return jsonify({'status': 'error', 'message': 'User not found'}), 404
            
            user.set_password(data.get('password'))
            db.session.commit()
            
            return jsonify({'status': 'success', 'message': 'Password has been reset successfully. You can now login with your new password.'}), 200
            
        except Exception as e:
            app.logger.error(f"Password reset error: {str(e)}")
            return jsonify({'status': 'error', 'message': 'An error occurred while resetting your password'}), 500
            
    return render_template('reset_password.html', token=token)

if __name__ == '__main__':
    app.run(debug=True)
