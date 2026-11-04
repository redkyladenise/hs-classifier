from flask import Blueprint

bp = Blueprint('main', __name__)

# This is a temporary home page
@bp.route('/')
def index():
    return "<h1>Hello! The website is working.</h1>"