from flask import jsonify, Blueprint
import logging

logger = logging.getLogger(__name__)

bp = Blueprint('main', __name__)

@bp.route('/')
def index():
    logger.info('Index request received')
    return jsonify({
        'message': 'Welcome to PowerPoint Generator API',
        'status': 'online'
    }), 200

@bp.route('/health')
def health():
    logger.info('Health check request received')
    return jsonify({
        'status': 'healthy',
        'version': '1.0.0'
    }), 200
