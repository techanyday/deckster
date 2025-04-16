from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for, flash
import os
from dotenv import load_dotenv
import logging
from utils import check_user_limits, get_max_slides, add_watermark, generate_presentation_content, create_ppt
from flask_wtf.csrf import CSRFProtect

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
    WTF_CSRF_ENABLED=True
)

# Initialize CSRF protection
csrf = CSRFProtect(app)

# Set OpenAI API key
import openai
if not os.getenv('OPENAI_API_KEY'):
    app.logger.error("OPENAI_API_KEY environment variable is not set!")
openai.api_key = os.getenv('OPENAI_API_KEY')

# Initialize extensions
from models import db, User, Presentation, SubscriptionPlan
db.init_app(app)

# Create database tables
with app.app_context():
    try:
        db.create_all()
        app.logger.info("Database tables created successfully")
    except Exception as e:
        app.logger.error(f"Error creating database tables: {str(e)}")

from flask_cors import CORS
CORS(app)

from flask_login import LoginManager, login_user, logout_user, login_required, current_user
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Import other dependencies
import tempfile
from datetime import datetime
import requests
from PIL import Image
from io import BytesIO

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

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
        data = request.get_json()
        if User.query.filter_by(email=data.get('email')).first():
            return jsonify({'status': 'error', 'message': 'Email already registered'}), 400
        
        user = User(
            email=data.get('email'),
            name=data.get('name')
        )
        user.set_password(data.get('password'))
        db.session.add(user)
        db.session.commit()
        login_user(user)
        return jsonify({'status': 'success'})
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/generate', methods=['POST'])
@login_required
def generate():
    if not check_user_limits(current_user):
        return jsonify({
            'status': 'error',
            'message': 'You have reached your presentation limit. Please upgrade your plan.'
        }), 400

    data = request.get_json()
    mode = data.get('mode', 'prompt')
    input_text = data.get('input')
    
    if not input_text:
        return jsonify({
            'status': 'error',
            'message': 'No input provided'
        }), 400

    content = generate_presentation_content(mode, input_text)
    if not content:
        return jsonify({
            'status': 'error',
            'message': 'Failed to generate presentation content'
        }), 500

    try:
        prs = create_ppt(content)
        
        # Add watermark for free users
        if current_user.subscription_type == 'free':
            add_watermark(prs)
        
        # Save to temporary file
        temp_ppt = tempfile.NamedTemporaryFile(delete=False, suffix='.pptx')
        prs.save(temp_ppt.name)
        
        # Save to database
        presentation = Presentation(
            title=f"Presentation {datetime.utcnow()}",
            content=content,
            file_path=temp_ppt.name,
            user_id=current_user.id
        )
        db.session.add(presentation)
        db.session.commit()
        
        return send_file(
            temp_ppt.name,
            as_attachment=True,
            download_name='presentation.pptx'
        )
    except Exception as e:
        app.logger.error(f"Error creating presentation: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'Failed to create presentation'
        }), 500

@app.route('/pricing')
def pricing():
    return render_template('pricing.html', plans=SubscriptionPlan.PLANS)

@app.route('/subscribe', methods=['POST'])
@login_required
def subscribe():
    data = request.get_json()
    plan = data.get('plan')
    
    if plan not in ['pro', 'business']:
        return jsonify({
            'status': 'error',
            'message': 'Invalid plan selected'
        }), 400

    # Get the appropriate plan ID from environment variables
    plan_id = os.getenv(f'PAYSTACK_PLAN_{plan.upper()}_MONTHLY')
    if not plan_id:
        return jsonify({
            'status': 'error',
            'message': 'Plan configuration error'
        }), 500

    try:
        # Initialize transaction with Paystack
        url = "https://api.paystack.co/transaction/initialize"
        headers = {
            "Authorization": f"Bearer {os.getenv('PAYSTACK_SECRET_KEY')}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "email": current_user.email,
            "plan": plan_id,
            "callback_url": url_for('payment_callback', _external=True)
        }
        
        response = requests.post(url, json=payload, headers=headers)
        response_data = response.json()
        
        if response_data['status']:
            return jsonify({
                'status': 'success',
                'authorization_url': response_data['data']['authorization_url']
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'Failed to initialize payment'
            }), 500
            
    except Exception as e:
        app.logger.error(f"Payment initialization error: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'An error occurred while processing your request'
        }), 500

@app.route('/payment/callback')
@login_required
def payment_callback():
    reference = request.args.get('reference')
    if not reference:
        flash('No reference supplied', 'error')
        return redirect(url_for('pricing'))
    
    try:
        # Verify the transaction
        verification = verify_paystack_transaction(reference)
        
        if verification['status']:
            # Update user's subscription
            data = verification['data']
            plan_code = data['plan']['plan_code']
            
            # Determine subscription type from plan code
            if plan_code == os.getenv('PAYSTACK_PLAN_PRO_MONTHLY'):
                current_user.subscription_type = 'pro'
            elif plan_code == os.getenv('PAYSTACK_PLAN_BUSINESS_MONTHLY'):
                current_user.subscription_type = 'business'
                
            current_user.subscription_reference = reference
            current_user.subscription_expires = datetime.fromtimestamp(data['paid_at'])
            db.session.commit()
            
            flash('Subscription successful!', 'success')
        else:
            flash('Payment verification failed', 'error')
            
    except Exception as e:
        app.logger.error(f"Payment verification error: {str(e)}")
        flash('An error occurred while verifying your payment', 'error')
        
    return redirect(url_for('pricing'))

if __name__ == '__main__':
    app.run(debug=True)
