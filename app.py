from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for, flash
from flask_cors import CORS
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
import openai
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.enum.text import PP_ALIGN
import os
from dotenv import load_dotenv
import tempfile
import json
import logging
import requests
from io import BytesIO
from PIL import Image
import base64
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash

from models import db, User, Presentation, SubscriptionPlan
from config import Config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.config.from_object(Config)
CORS(app)
db.init_app(app)

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def check_user_limits(user):
    """Check if user has reached their presentation limits."""
    if user.subscription_type == 'free':
        # Check weekly limit for free users
        week_ago = datetime.utcnow() - timedelta(days=7)
        weekly_count = Presentation.query.filter(
            Presentation.user_id == user.id,
            Presentation.created_at >= week_ago
        ).count()
        return weekly_count < Config.FREE_WEEKLY_LIMIT
    elif user.subscription_type == 'pro':
        # Check monthly limit for pro users
        month_ago = datetime.utcnow() - timedelta(days=30)
        monthly_count = Presentation.query.filter(
            Presentation.user_id == user.id,
            Presentation.created_at >= month_ago
        ).count()
        return monthly_count < Config.PRO_MONTHLY_LIMIT
    elif user.subscription_type == 'business':
        month_ago = datetime.utcnow() - timedelta(days=30)
        monthly_count = Presentation.query.filter(
            Presentation.user_id == user.id,
            Presentation.created_at >= month_ago
        ).count()
        return monthly_count < Config.BUSINESS_MONTHLY_LIMIT
    return False

def get_max_slides(user):
    """Get maximum allowed slides based on user's subscription."""
    return SubscriptionPlan.PLANS[user.subscription_type]['max_slides']

def add_watermark(prs):
    """Add watermark to presentation if user is on free plan."""
    for slide in prs.slides:
        left = Inches(0.5)
        top = prs.slide_height - Inches(0.5)
        width = Inches(4)
        height = Inches(0.3)
        
        txBox = slide.shapes.add_textbox(left, top, width, height)
        tf = txBox.text_frame
        tf.text = "Created with PowerPoint Generator"
        tf.paragraphs[0].font.size = Pt(10)
        tf.paragraphs[0].font.color.rgb = RGBColor(128, 128, 128)

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
        logger.error(f"Error generating image: {str(e)}")
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
        logger.error(f"Error creating image prompt: {str(e)}")
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
        logger.error(f"Error extracting keywords: {str(e)}")
        return None

def generate_presentation_content(mode, input_text):
    """Generate presentation content based on mode and input."""
    system_prompt = """You are a presentation expert. Create a detailed presentation with 5 slides. 
For each slide, provide:
1. A clear, engaging title (without slide numbers)
2. 3-4 detailed bullet points with actual content (not just topics)
3. Each bullet point should be a complete thought/sentence
4. Include relevant examples, statistics, or real-world applications where appropriate
5. Make the content engaging and presentation-friendly

Format each slide as:
First Slide:
Presentation Title
• Subtitle or tagline

Subsequent Slides:
Title
• Detailed point 1
• Detailed point 2
• Detailed point 3
• Optional point 4

Make sure the content flows naturally from one slide to the next."""

    if mode == 'prompt':
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Create a detailed, engaging presentation about: {input_text}"}
        ]
    else:  # mode == 'content'
        messages = [
            {"role": "system", "content": system_prompt + "\nUse the provided content as source material, extracting and organizing the most important points into a coherent presentation."},
            {"role": "user", "content": f"Create a presentation from this content: {input_text}"}
        ]

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=messages,
            temperature=0.7
        )
        return response.choices[0].message['content']
    except Exception as e:
        logger.error(f"Error generating content: {str(e)}")
        return None

def create_ppt(content):
    """Create a PowerPoint presentation with AI-generated images."""
    prs = Presentation()
    
    # Set slide width and height (standard 16:9 aspect ratio)
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    
    slides = content.split('\n\n')
    for i, slide_content in enumerate(slides):
        if not slide_content.strip():
            continue
            
        if i == 0:  # Title slide
            slide = prs.slides.add_slide(prs.slide_layouts[0])
            
            # Create title shape
            left = Inches(0.5)
            top = Inches(1)
            width = prs.slide_width - Inches(1)
            height = Inches(2)
            
            title_box = slide.shapes.add_textbox(left, top, width, height)
            title_frame = title_box.text_frame
            title_frame.word_wrap = False
            
            # Add subtitle shape
            subtitle_top = top + Inches(2.5)
            subtitle_height = Inches(1.5)
            subtitle_box = slide.shapes.add_textbox(left, subtitle_top, width, subtitle_height)
            subtitle_frame = subtitle_box.text_frame
            subtitle_frame.word_wrap = True
            
            lines = slide_content.strip().split('\n')
            if lines:
                # Add title text
                title_para = title_frame.paragraphs[0]
                title_para.text = lines[0].replace('First Slide:', '').replace('Slide 1:', '').strip()
                title_para.alignment = PP_ALIGN.CENTER
                title_para.font.size = Pt(44)
                
                # Add subtitle if present
                if len(lines) > 1:
                    subtitle_para = subtitle_frame.paragraphs[0]
                    subtitle_para.text = lines[1].strip('• ').strip()
                    subtitle_para.alignment = PP_ALIGN.CENTER
                    subtitle_para.font.size = Pt(32)
                
                # Add a relevant image based on the title
                prompt = extract_image_prompt(lines[0])
                if prompt:
                    image_path = generate_image(prompt)
                    if image_path:
                        # Add image to the background
                        left = Inches(0)
                        top = Inches(0)
                        width = prs.slide_width
                        height = prs.slide_height
                        slide.shapes.add_picture(image_path, left, top, width, height)
                        os.unlink(image_path)  # Clean up
                        
                        # Move image to back
                        slide.shapes[0].element.addprevious(slide.shapes[-1].element)
        else:
            slide = prs.slides.add_slide(prs.slide_layouts[1])
            
            # Create title shape
            left = Inches(0.5)
            top = Inches(0.5)
            width = prs.slide_width - Inches(1)
            height = Inches(1.2)
            
            title_box = slide.shapes.add_textbox(left, top, width, height)
            title_frame = title_box.text_frame
            title_frame.word_wrap = False
            
            # Create content shape
            content_top = top + height + Inches(0.2)
            content_height = prs.slide_height - content_top - Inches(0.5)
            content_box = slide.shapes.add_textbox(
                left + Inches(0.5),
                content_top,
                width - Inches(5),  # Make room for image
                content_height
            )
            content_frame = content_box.text_frame
            content_frame.word_wrap = True
            
            lines = slide_content.strip().split('\n')
            if lines:
                # Add title
                title_para = title_frame.paragraphs[0]
                title_para.text = lines[0].strip()
                title_para.alignment = PP_ALIGN.LEFT
                title_para.font.size = Pt(40)
                
                # Add content
                first_para = True
                for line in lines[1:]:
                    if not line.strip():
                        continue
                    
                    p = content_frame.add_paragraph()
                    p.text = line.strip('• ').strip()
                    p.font.size = Pt(24)
                    p.level = 0
                    
                    if not first_para:
                        p.space_before = Pt(12)
                    first_para = False
                
                # Add a relevant image based on the slide content
                prompt = extract_image_prompt(slide_content)
                if prompt:
                    image_path = generate_image(prompt)
                    if image_path:
                        # Add image on the right side
                        image_width = Inches(4.5)
                        image_height = Inches(4)
                        image_left = prs.slide_width - image_width - Inches(0.5)
                        image_top = content_top
                        slide.shapes.add_picture(image_path, image_left, image_top, image_width, image_height)
                        os.unlink(image_path)  # Clean up

    # Save to temporary file
    temp_file = os.path.join(tempfile.gettempdir(), f"presentation_{hash(str(content))}.pptx")
    try:
        prs.save(temp_file)
        return os.path.basename(temp_file)
    except Exception as e:
        logger.error(f"Error saving presentation: {str(e)}")
        raise

@app.route('/')
def index():
    """Render the main page."""
    return render_template('index.html',
                         plans=SubscriptionPlan.PLANS,
                         paystack_public_key=app.config['PAYSTACK_PUBLIC_KEY'])

@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    
    if User.query.filter_by(email=data['email']).first():
        return jsonify({'error': 'Email already registered'}), 400
        
    user = User(
        email=data['email'],
        name=data['name'],
        password_hash=generate_password_hash(data['password'])
    )
    db.session.add(user)
    db.session.commit()
    
    login_user(user)
    return jsonify({'message': 'Registration successful'})

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    user = User.query.filter_by(email=data['email']).first()
    
    if user and check_password_hash(user.password_hash, data['password']):
        login_user(user)
        return jsonify({'message': 'Login successful'})
    
    return jsonify({'error': 'Invalid credentials'}), 401

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/subscribe', methods=['POST'])
@login_required
def subscribe():
    data = request.get_json()
    plan = data.get('plan')
    
    if plan not in SubscriptionPlan.PLANS:
        return jsonify({'error': 'Invalid plan'}), 400
    
    try:
        # Create Paystack transaction
        url = "https://api.paystack.co/transaction/initialize"
        headers = {
            "Authorization": f"Bearer {app.config['PAYSTACK_SECRET_KEY']}",
            "Content-Type": "application/json"
        }
        
        plan_id = app.config['PAYSTACK_PLAN_IDS'].get(f'{plan}_monthly')
        if not plan_id:
            return jsonify({'error': 'Invalid plan ID'}), 400
            
        payload = {
            "email": current_user.email,
            "plan": plan_id,
            "currency": "USD",  # Specify USD currency
            "callback_url": request.host_url + 'payment/verify'
        }
        
        response = requests.post(url, headers=headers, json=payload)
        data = response.json()
        
        if data['status']:
            return jsonify({
                'status': 'success',
                'authorization_url': data['data']['authorization_url']
            })
        else:
            return jsonify({'error': 'Failed to initialize transaction'}), 500
            
    except Exception as e:
        logger.error(f"Error creating payment: {str(e)}")
        return jsonify({'error': 'Unable to process payment'}), 500

@app.route('/payment/verify')
@login_required
def verify_payment():
    reference = request.args.get('reference')
    if not reference:
        return jsonify({'error': 'No reference provided'}), 400
        
    try:
        # Verify the transaction
        verification = verify_paystack_transaction(reference)
        
        if verification['status'] and verification['data']['status'] == 'success':
            # Update user subscription
            plan_code = verification['data']['plan']['plan_code']
            
            # Find the plan type from the plan code
            for plan_type, code in app.config['PAYSTACK_PLAN_IDS'].items():
                if code == plan_code:
                    current_user.subscription_type = plan_type.replace('_monthly', '')
                    db.session.commit()
                    flash('Subscription updated successfully!')
                    break
                    
            return redirect(url_for('index'))
        else:
            flash('Payment verification failed!')
            return redirect(url_for('index'))
            
    except Exception as e:
        logger.error(f"Error verifying payment: {str(e)}")
        flash('Error verifying payment!')
        return redirect(url_for('index'))

@app.route('/pricing')
def pricing():
    """Show pricing page."""
    return render_template('pricing.html',
                         plans=SubscriptionPlan.PLANS,
                         paystack_public_key=app.config['PAYSTACK_PUBLIC_KEY'])

@app.route('/payment/success')
@login_required
def payment_success():
    """Handle successful payment."""
    return render_template('payment_success.html')

@app.route('/payment/failed')
@login_required
def payment_failed():
    """Handle failed payment."""
    return render_template('payment_failed.html')

@app.route('/generate', methods=['POST'])
@login_required
def generate():
    """Generate a presentation from prompt or content."""
    try:
        # Check user limits
        if not check_user_limits(current_user):
            return jsonify({'error': 'You have reached your presentation limit'}), 403
        
        # Get generation mode and input
        mode = request.form.get('mode', '').strip()
        if mode not in ['prompt', 'content']:
            return jsonify({'error': 'Invalid mode. Must be "prompt" or "content"'}), 400
            
        input_text = request.form.get('input', '').strip()
        if not input_text:
            return jsonify({'error': 'Please provide input text'}), 400
        
        # Generate presentation content
        try:
            content = generate_presentation_content(mode, input_text)
            if not content:
                return jsonify({'error': 'Failed to generate presentation content'}), 500
                
            # Check slide count
            slides = content.split('\n\n')
            max_slides = get_max_slides(current_user)
            if len(slides) > max_slides:
                return jsonify({'error': f'Slide count exceeds your plan limit of {max_slides} slides'}), 403
        except Exception as e:
            logger.error(f"Error generating content: {str(e)}")
            return jsonify({'error': 'Failed to generate presentation content. Please try again.'}), 500
            
        # Create PowerPoint file
        try:
            filename = create_ppt(content)
            
            # Save presentation record
            presentation = Presentation(
                title=slides[0].split('\n')[0].strip(),
                content=content,
                slides_count=len(slides),
                file_path=filename,
                user_id=current_user.id
            )
            db.session.add(presentation)
            db.session.commit()
            
            return jsonify({
                'message': 'Presentation generated successfully',
                'content': content,
                'filename': filename
            })
        except Exception as e:
            logger.error(f"Error creating PowerPoint: {str(e)}")
            return jsonify({'error': 'Failed to create PowerPoint file. Please try again.'}), 500
            
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return jsonify({'error': 'An unexpected error occurred. Please try again.'}), 500

@app.route('/download/<filename>')
@login_required
def download(filename):
    """Download a generated presentation."""
    try:
        # Verify the presentation belongs to the user
        presentation = Presentation.query.filter_by(
            file_path=filename,
            user_id=current_user.id
        ).first()
        
        if not presentation:
            return jsonify({'error': 'Presentation not found'}), 404
        
        file_path = os.path.join(tempfile.gettempdir(), filename)
        if not os.path.exists(file_path):
            return jsonify({'error': 'File not found'}), 404
            
        return send_file(
            file_path,
            as_attachment=True,
            download_name='presentation.pptx'
        )
    except Exception as e:
        logger.error(f"Error downloading file: {str(e)}")
        return jsonify({'error': 'Error downloading file'}), 500

@app.route('/health')
def health_check():
    """Check the health status of the application."""
    try:
        if not openai.api_key:
            raise ValueError("OpenAI API key not configured")
            
        # Verify temp directory exists and is writable
        if not os.path.exists(tempfile.gettempdir()) or not os.access(tempfile.gettempdir(), os.W_OK):
            raise ValueError("Temp directory not accessible")
            
        # Check database connection
        db.session.execute('SELECT 1')
            
        return jsonify({
            'status': 'healthy',
            'temp_dir': os.path.exists(tempfile.gettempdir()),
            'database': 'connected'
        })
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return jsonify({'status': 'unhealthy', 'error': str(e)}), 500

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
