from flask import Flask, render_template

def create_app():
    app = Flask(__name__)
    app.config['MAX_CONTENT_LENGTH'] = 8 * 1024

    # Connect the routes
    from app import routes
    app.register_blueprint(routes.bp)

    # --- Error Handlers ---
    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('404.html'), 404

    @app.errorhandler(500)
    def internal_error(error):
        return render_template('500.html'), 500

    # --- Security Headers ---
    @app.after_request
    def add_security_headers(response):
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "script-src 'self'; "
            "frame-ancestors 'none';"
        )
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['X-Frame-Options'] = 'DENY'
        return response

    app.config['USE_STUB'] = False
    app.config['MAX_BATCH_ROWS'] = 200
    app.config['BATCH_CHUNK'] = 5
    app.config['MAX_CHARS'] = 500
    
    return app