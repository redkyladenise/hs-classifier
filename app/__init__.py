from flask import Flask

def create_app():
    # This creates the website app
    app = Flask(__name__)
    
    # This limits how much text someone can send at once (8 KB max)
    app.config['MAX_CONTENT_LENGTH'] = 8 * 1024

    # Connect the pages (routes)
    from app import routes
    app.register_blueprint(routes.bp)

    return app