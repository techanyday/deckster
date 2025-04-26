from flask import Flask, render_template, request, send_file, jsonify, session, redirect, url_for, flash
from text_generation import TextGenerator
from slides_generator import SlidesGenerator
from payment_handler import PaystackHandler, PaymentSession
from flask_bootstrap import Bootstrap
from flask_wtf.csrf import CSRFProtect
from flask_wtf import FlaskForm
import os
from datetime import datetime
import uuid
from dotenv import load_dotenv
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-123')
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'temp_presentations')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize extensions
bootstrap = Bootstrap(app)
csrf = CSRFProtect(app)

# Initialize handlers
try:
    text_generator = TextGenerator()
    slides_generator = SlidesGenerator()
    paystack_handler = PaystackHandler()
    logger.info("Successfully initialized all handlers")
except Exception as e:
    logger.error(f"Error initializing handlers: {str(e)}", exc_info=True)
    raise

# Payment amount in GHS (or your preferred currency)
PAYMENT_AMOUNT = 20.00

# Create a simple form for CSRF protection
class EmptyForm(FlaskForm):
    pass

@app.before_request
def check_session():
    """Ensure user has a session ID and payment session."""
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
        logger.debug(f"Created new session ID: {session['session_id']}")
    if 'payment_session' not in session:
        session['payment_session'] = PaymentSession(session['session_id']).__dict__
        logger.debug("Created new payment session")

def get_payment_session() -> PaymentSession:
    """Get or create payment session for the current user."""
    if 'payment_session' in session:
        # Convert dict back to PaymentSession object
        data = session['payment_session']
        payment_session = PaymentSession(data['session_id'])
        payment_session.__dict__.update(data)
        logger.debug(f"Retrieved payment session: {payment_session.__dict__}")
        return payment_session
    return PaymentSession(session['session_id'])

def save_payment_session(payment_session: PaymentSession):
    """Save payment session to Flask session."""
    session['payment_session'] = payment_session.__dict__
    session.modified = True
    logger.debug(f"Saved payment session: {payment_session.__dict__}")

@app.route('/')
def index():
    form = EmptyForm()
    logger.debug("Rendering index page with CSRF form")
    return render_template('index.html', form=form)

@app.route('/generate', methods=['POST'])
def generate():
    try:
        logger.info("Starting presentation generation")
        logger.debug(f"Form data: {request.form}")
        
        topic = request.form.get('topic')
        if not topic:
            logger.warning("No topic provided in form data")
            return jsonify({'error': 'No topic provided'}), 400

        # Get payment session
        payment_session = get_payment_session()
        logger.info(f"Payment session: {payment_session.__dict__}")
        
        # Check if user can generate more slides
        can_continue, message = payment_session.increment_slides()
        if not can_continue:
            save_payment_session(payment_session)
            logger.info("User reached free limit")
            return jsonify({
                'error': message,
                'payment_required': True
            }), 402

        # Generate content
        logger.info(f"Generating content for topic: {topic}")
        try:
            content = text_generator(topic, max_slides=5 if not payment_session.payment_status else 10)
            logger.debug(f"Generated content: {content}")
        except Exception as e:
            logger.error(f"Text generation error: {str(e)}", exc_info=True)
            return jsonify({'error': str(e)}), 500

        # Create unique filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"presentation_{timestamp}.pptx"
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

        # Generate presentation
        logger.info(f"Generating presentation at: {output_path}")
        try:
            slides_generator.generate_presentation(content, output_path)
            logger.info("Presentation generated successfully")
        except Exception as e:
            logger.error(f"Slides generation error: {str(e)}", exc_info=True)
            return jsonify({'error': str(e)}), 500
        
        # Save session
        save_payment_session(payment_session)

        return jsonify({
            'success': True,
            'filename': filename,
            'message': message,
            'payment_status': payment_session.payment_status
        })

    except Exception as e:
        logger.error(f"Error generating presentation: {str(e)}", exc_info=True)
        return jsonify({
            'error': str(e) if app.debug else 'Something went wrong, please try again later'
        }), 500

@app.route('/payment/initialize', methods=['POST'])
def initialize_payment():
    try:
        logger.info("Starting payment initialization")
        logger.debug(f"Form data: {request.form}")
        
        email = request.form.get('email')
        if not email:
            logger.warning("No email provided in form data")
            return jsonify({'error': 'Email is required'}), 400

        # Initialize payment
        success, message, auth_url = paystack_handler.initialize_payment(email, PAYMENT_AMOUNT)
        logger.info(f"Payment initialization result: success={success}, message={message}")
        
        if success and auth_url:
            return jsonify({
                'success': True,
                'authorization_url': auth_url
            })
        
        return jsonify({
            'error': message
        }), 400

    except Exception as e:
        logger.error(f"Payment initialization error: {str(e)}", exc_info=True)
        return jsonify({
            'error': str(e) if app.debug else 'Failed to initialize payment'
        }), 500

@app.route('/payment/callback')
def payment_callback():
    try:
        logger.info("Processing payment callback")
        logger.debug(f"Callback args: {request.args}")
        
        reference = request.args.get('reference')
        if not reference:
            logger.warning("No reference provided in callback")
            flash('Payment verification failed: No reference provided', 'error')
            return redirect(url_for('index'))

        # Verify payment
        success, message, transaction_data = paystack_handler.verify_payment(reference)
        logger.info(f"Payment verification result: success={success}, message={message}")
        
        if success:
            # Update payment session
            payment_session = get_payment_session()
            payment_session.complete_payment()
            save_payment_session(payment_session)
            
            flash('Payment successful! You now have unlimited access.', 'success')
        else:
            flash(f'Payment verification failed: {message}', 'error')

        return redirect(url_for('index'))
    except Exception as e:
        logger.error(f"Payment callback error: {str(e)}", exc_info=True)
        flash('An error occurred while processing your payment', 'error')
        return redirect(url_for('index'))

@app.route('/download/<filename>')
def download(filename):
    try:
        logger.info(f"Starting download for file: {filename}")
        # Check payment status
        payment_session = get_payment_session()
        if not payment_session.payment_status:
            logger.warning("Unpaid user attempted to download file")
            return jsonify({
                'error': 'Payment required to download presentations'
            }), 402

        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            raise FileNotFoundError('Presentation file not found')

        logger.info(f"Sending file: {file_path}")
        return send_file(
            file_path,
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        logger.error(f"Download error: {str(e)}", exc_info=True)
        return jsonify({
            'error': str(e) if app.debug else 'File not found'
        }), 404

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
