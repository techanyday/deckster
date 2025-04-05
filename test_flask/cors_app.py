from flask import Flask
from flask_cors import CORS
import logging

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes
app.config['DEBUG'] = True

@app.route('/')
def hello():
    logger.debug('Handling request to /')
    return {'message': 'Hello from Flask!'}, 200

@app.route('/health')
def health():
    logger.debug('Handling health check request')
    return {'status': 'healthy'}, 200

if __name__ == '__main__':
    logger.info('Starting Flask application with CORS...')
    app.run(debug=True, host='127.0.0.1', port=5000)
