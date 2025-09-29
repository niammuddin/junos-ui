import os
from flask import Flask, redirect, url_for, render_template
from src.utils.database import init_db
from src.auth.security import init_login_manager, limiter
from src.auth.routes import auth_bp
from src.juniper.routes import juniper_bp
from config import Config

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    
    # Initialize extensions
    init_db()
    init_login_manager(app)
    limiter.init_app(app)
    
    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(juniper_bp, url_prefix='/juniper')
    
    # Simple root route
    @app.route('/')
    def index():
        return redirect(url_for('auth.login'))
    
    # Error handlers
    @app.errorhandler(404)
    def not_found(error):
        return render_template('404.html'), 404

    @app.errorhandler(403)
    def forbidden(error):
        from flask import flash
        flash('Anda tidak memiliki akses ke halaman ini!', 'danger')
        return redirect(url_for('auth.dashboard'))

    @app.errorhandler(429)
    def ratelimit_handler(e):
        from flask import flash
        flash('Terlalu banyak percobaan login. Coba lagi setelah 1 menit.', 'danger')
        return redirect(url_for('auth.login'))

    @app.errorhandler(500)
    def internal_error(error):
        from flask import flash
        flash('Terjadi kesalahan server. Silakan coba lagi.', 'danger')
        return redirect(url_for('auth.dashboard'))
    
    # Context processors
    @app.context_processor
    def utility_processor():
        from flask import json as flask_json
        return {'tojson': flask_json.dumps}
    
    @app.context_processor
    def inject_stats():
        from flask_login import current_user
        if current_user.is_authenticated:
            try:
                from src.utils.database import get_database_stats
                from src.models.device import get_juniper_devices_count
                return {
                    'stats': get_database_stats(),
                    'devices_count': get_juniper_devices_count()
                }
            except:
                return {}
        return {}
    
    # Security headers
    @app.after_request
    def set_security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        return response
    
    return app

if __name__ == '__main__':
    app = create_app()
    print("🚀 Starting Juniper Login System...")
    app.run(debug=True, host='0.0.0.0', port=5000)