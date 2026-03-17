"""
MiroFish Backend - Flask application factory.
"""

import os
import warnings

# Suppress multiprocessing resource_tracker warnings (from third-party libs like transformers)
# Must be set before all other imports
warnings.filterwarnings("ignore", message=".*resource_tracker.*")

from flask import Flask, request, jsonify
from flask_cors import CORS

from .config import Config
from .utils.logger import setup_logger, get_logger


def create_app(config_class=Config):
    """Flask application factory function."""
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # Set JSON encoding: ensure non-ASCII characters display directly (not \uXXXX format)
    # Flask >= 2.3 uses app.json.ensure_ascii; older versions use JSON_AS_ASCII
    if hasattr(app, 'json') and hasattr(app.json, 'ensure_ascii'):
        app.json.ensure_ascii = False
    
    # Set up logging
    logger = setup_logger('mirofish')
    
    # Print startup logs only in the reloader subprocess (avoid duplicate logs in debug mode)
    is_reloader_process = os.environ.get('WERKZEUG_RUN_MAIN') == 'true'
    debug_mode = app.config.get('DEBUG', False)
    should_log_startup = not debug_mode or is_reloader_process
    
    if should_log_startup:
        logger.info("=" * 50)
        logger.info("MiroFish Backend starting...")
        logger.info("=" * 50)
    
    # Enable CORS
    CORS(app, resources={r"/api/*": {"origins": "*"}})
    
    # Register simulation process cleanup (ensure all simulation processes stop on server shutdown)
    from .services.simulation_runner import SimulationRunner
    SimulationRunner.register_cleanup()
    if should_log_startup:
        logger.info("Simulation process cleanup registered")
    
    # API key authentication
    api_key = app.config.get('API_KEY')
    if not api_key:
        import warnings
        warnings.warn("API_KEY is not set — all endpoints are unprotected", stacklevel=2)

    @app.before_request
    def require_api_key():
        if not api_key:
            return
        # Skip auth for health check
        if request.path == '/health' or request.method == 'OPTIONS':
            return
        if request.headers.get('X-API-Key') != api_key:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 401

    # Request logging middleware
    @app.before_request
    def log_request():
        logger = get_logger('mirofish.request')
        logger.debug(f"Request: {request.method} {request.path}")
        if request.content_type and 'json' in request.content_type:
            logger.debug(f"Request body: {request.get_json(silent=True)}")
    
    @app.after_request
    def log_response(response):
        logger = get_logger('mirofish.request')
        logger.debug(f"Response: {response.status_code}")
        return response
    
    # Register blueprints
    from .api import graph_bp, simulation_bp, report_bp
    app.register_blueprint(graph_bp, url_prefix='/api/graph')
    app.register_blueprint(simulation_bp, url_prefix='/api/simulation')
    app.register_blueprint(report_bp, url_prefix='/api/report')
    
    # Health check
    @app.route('/health')
    def health():
        return {'status': 'ok', 'service': 'MiroFish Backend'}
    
    if should_log_startup:
        logger.info("MiroFish Backend started")
    
    return app

