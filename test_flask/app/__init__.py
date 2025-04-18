from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_cors import CORS
import logging

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize extensions
db = SQLAlchemy()
login_manager = LoginManager()

def create_app():
    app = Flask(__name__)
    logger.info('Creating Flask application...')
    
    # Configure the app
    app.config.update(
        SECRET_KEY='dev-secret-key-123',
        SQLALCHEMY_DATABASE_URI='sqlite:///app.db',
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        DEBUG=True
    )
    logger.info('App configuration complete')
    
    # Initialize extensions
    CORS(app)
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    logger.info('Extensions initialized')
    
    # Import models
    from . import models
    
    @login_manager.user_loader
    def load_user(user_id):
        return models.User.query.get(int(user_id))
    
    with app.app_context():
        try:
            # Import and register blueprints
            from .routes.main import bp as main_bp
            from .routes.auth import bp as auth_bp
            from .routes.presentation import bp as presentation_bp
            
            app.register_blueprint(main_bp)
            app.register_blueprint(auth_bp, url_prefix='/auth')
            app.register_blueprint(presentation_bp, url_prefix='/presentations')
            
            # Log all registered routes
            logger.info('Registered routes:')
            for rule in app.url_map.iter_rules():
                logger.info(f'  {rule.rule} -> {rule.endpoint} [{", ".join(rule.methods)}]')
            
            logger.info('Routes registered successfully')
            
            # Create database tables
            db.create_all()
            logger.info('Database tables created successfully')
            
        except Exception as e:
            logger.error(f'Error during app initialization: {str(e)}')
            raise
        
        @app.after_request
        def after_request(response):
            logger.debug(f'Request completed: {response.status}')
            return response
        
        return app
