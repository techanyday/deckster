from flask import Flask
import logging

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

@app.route('/')
def hello():
    logger.info('Handling request to /')
    return 'Hello from Flask!'

@app.route('/health')
def health():
    logger.info('Handling health check request')
    return 'OK'

if __name__ == '__main__':
    logger.info('Starting Flask application...')
    try:
        app.run(host='127.0.0.1', port=5000)
    except Exception as e:
        logger.error(f'Error starting Flask app: {str(e)}')
