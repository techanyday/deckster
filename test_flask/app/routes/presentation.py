from flask import jsonify, request, Blueprint
from flask_login import current_user, login_required
from ..models import Presentation, db
import logging

logger = logging.getLogger(__name__)

bp = Blueprint('presentations', __name__)

@bp.route('/', methods=['GET'])
@login_required
def list_presentations():
    logger.info('Listing presentations for user')
    try:
        presentations = Presentation.query.filter_by(user_id=current_user.id).all()
        return jsonify({
            'presentations': [{
                'id': p.id,
                'title': p.title,
                'content': p.content,
                'created_at': p.created_at.isoformat(),
                'updated_at': p.updated_at.isoformat() if p.updated_at else None
            } for p in presentations]
        }), 200
    except Exception as e:
        logger.error(f'Error listing presentations: {str(e)}')
        return jsonify({'error': 'Failed to list presentations'}), 500

@bp.route('/', methods=['POST'])
@login_required
def create_presentation():
    logger.info('Creating new presentation')
    try:
        data = request.get_json()
        logger.debug(f'Presentation creation data: {data}')
        
        if not data:
            logger.error('No JSON data in request')
            return jsonify({'error': 'No JSON data provided'}), 400
            
        if 'title' not in data:
            logger.error('Missing title in presentation creation request')
            return jsonify({'error': 'Title is required'}), 400
        
        try:
            presentation = Presentation(
                title=data['title'],
                content=data.get('content', ''),
                user_id=current_user.id
            )
            
            db.session.add(presentation)
            db.session.commit()
            
            logger.info(f'Presentation created successfully: {presentation.id}')
            return jsonify({
                'message': 'Presentation created successfully',
                'presentation': {
                    'id': presentation.id,
                    'title': presentation.title,
                    'content': presentation.content,
                    'created_at': presentation.created_at.isoformat(),
                    'updated_at': presentation.updated_at.isoformat() if presentation.updated_at else None
                }
            }), 201
        except Exception as e:
            logger.error(f'Database error during presentation creation: {str(e)}')
            db.session.rollback()
            return jsonify({'error': 'Failed to create presentation'}), 500
    except Exception as e:
        logger.error(f'Unexpected error during presentation creation: {str(e)}')
        return jsonify({'error': 'Internal server error'}), 500

@bp.route('/<int:id>', methods=['GET'])
@login_required
def get_presentation(id):
    logger.info(f'Getting presentation {id}')
    try:
        presentation = Presentation.query.filter_by(id=id, user_id=current_user.id).first()
        
        if not presentation:
            logger.warning(f'Presentation {id} not found')
            return jsonify({'error': 'Presentation not found'}), 404
            
        return jsonify({
            'presentation': {
                'id': presentation.id,
                'title': presentation.title,
                'content': presentation.content,
                'created_at': presentation.created_at.isoformat(),
                'updated_at': presentation.updated_at.isoformat() if presentation.updated_at else None
            }
        }), 200
    except Exception as e:
        logger.error(f'Error getting presentation: {str(e)}')
        return jsonify({'error': 'Failed to get presentation'}), 500
