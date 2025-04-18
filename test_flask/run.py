import os
import sys
import logging
from urllib.parse import unquote

# Add the parent directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
import logging

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = create_app()

if __name__ == '__main__':
    # Print all registered routes
    print('\nRegistered routes:')
    for rule in app.url_map.iter_rules():
        print(f'  {rule.rule} -> {rule.endpoint} [{", ".join(rule.methods)}]')
    
    logger.info('Starting development server...')
    app.run(host='127.0.0.1', port=5000, debug=True)
