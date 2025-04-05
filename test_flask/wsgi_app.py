from flask import Flask
import logging

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create Flask app with explicit instance path
app = Flask(__name__, 
           instance_relative_config=True,
           static_url_path='')

# Basic configuration
app.config.update(
    ENV='development',
    DEBUG=True,
    TESTING=True
)

@app.route('/')
def index():
    logger.info('Handling request to /')
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Flask Test</title>
    </head>
    <body>
        <h1>Hello from Flask!</h1>
        <p>The server is working correctly.</p>
        <p><a href="/health">Check Health</a></p>
    </body>
    </html>
    '''

@app.route('/health')
def health():
    logger.info('Handling health check request')
    return 'OK'

if __name__ == '__main__':
    logger.info('Starting Flask application...')
    app.run(host='127.0.0.1', port=5000, debug=True, use_reloader=False)
