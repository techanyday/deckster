from flask import Flask, jsonify
from flask_cors import CORS
import logging

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})  # Enable CORS for all routes
app.config['DEBUG'] = True

@app.route('/')
def hello():
    logger.debug('Handling request to /')
    response = jsonify({'message': 'Hello from Flask!'})
    return response

@app.route('/health')
def health():
    logger.debug('Handling health check request')
    response = jsonify({'status': 'healthy'})
    return response

if __name__ == '__main__':
    logger.info('Starting Flask application...')
    # Listen on all available interfaces
    app.run(debug=True, host='0.0.0.0', port=5000)
