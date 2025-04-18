from flask import jsonify, request, Blueprint
from flask_login import login_user, logout_user, login_required
from ..models import User, db
import logging

logger = logging.getLogger(__name__)

bp = Blueprint('auth', __name__)

@bp.route('/register', methods=['POST'])
def register():
    logger.info('Handling registration request')
    try:
        data = request.get_json()
        logger.debug(f'Registration request data: {data}')
        
        if not data:
            logger.error('No JSON data in request')
            return jsonify({'error': 'No JSON data provided'}), 400
            
        if 'email' not in data or 'password' not in data:
            logger.error('Missing required fields in registration request')
            return jsonify({'error': 'Email and password are required'}), 400
        
        if User.query.filter_by(email=data['email']).first():
            logger.warning(f'Email already registered: {data["email"]}')
            return jsonify({'error': 'Email already registered'}), 400
            
        try:
            user = User(
                email=data['email'],
                name=data.get('name', '')
            )
            user.set_password(data['password'])
            
            db.session.add(user)
            db.session.commit()
            
            login_user(user)
            logger.info(f'User registered successfully: {user.email}')
            return jsonify({
                'message': 'Registration successful',
                'user': {
                    'id': user.id,
                    'email': user.email,
                    'name': user.name
                }
            }), 201
        except Exception as e:
            logger.error(f'Database error during registration: {str(e)}')
            db.session.rollback()
            return jsonify({'error': 'Registration failed'}), 500
    except Exception as e:
        logger.error(f'Unexpected error during registration: {str(e)}')
        return jsonify({'error': 'Internal server error'}), 500

@bp.route('/login', methods=['POST'])
def login():
    logger.info('Handling login request')
    try:
        data = request.get_json()
        logger.debug(f'Login request data: {data}')
        
        if not data:
            logger.error('No JSON data in request')
            return jsonify({'error': 'No JSON data provided'}), 400
        
        if 'email' not in data or 'password' not in data:
            logger.error('Missing required fields in login request')
            return jsonify({'error': 'Email and password are required'}), 400
        
        user = User.query.filter_by(email=data['email']).first()
        
        if user and user.check_password(data['password']):
            login_user(user)
            logger.info(f'User logged in successfully: {user.email}')
            return jsonify({
                'message': 'Login successful',
                'user': {
                    'id': user.id,
                    'email': user.email,
                    'name': user.name
                }
            }), 200
        
        logger.warning(f'Failed login attempt for email: {data.get("email")}')
        return jsonify({'error': 'Invalid email or password'}), 401
    except Exception as e:
        logger.error(f'Unexpected error during login: {str(e)}')
        return jsonify({'error': 'Internal server error'}), 500

@bp.route('/logout', methods=['POST'])
@login_required
def logout():
    logger.info('Handling logout request')
    try:
        logout_user()
        return jsonify({'message': 'Logged out successfully'}), 200
    except Exception as e:
        logger.error(f'Error during logout: {str(e)}')
        return jsonify({'error': 'Logout failed'}), 500
