from flask import Flask
import logging

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['DEBUG'] = True

@app.route('/')
def hello():
    try:
        logger.debug('Handling request to /')
        return 'Hello from Flask Debug!'
    except Exception as e:
        logger.error(f'Error in hello route: {str(e)}')
        return f'Error: {str(e)}', 500

@app.route('/test')
def test():
    try:
        logger.debug('Handling request to /test')
        return 'Test route working!'
    except Exception as e:
        logger.error(f'Error in test route: {str(e)}')
        return f'Error: {str(e)}', 500

if __name__ == '__main__':
    logger.info('Starting Flask application...')
    app.run(debug=True, host='127.0.0.1', port=5000)
