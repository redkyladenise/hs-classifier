from flask import Blueprint, redirect, url_for

bp = Blueprint('main', __name__)

@bp.route('/')
def index():
    return redirect(url_for('main.about'))

@bp.route('/about')
def about():
    return "<h1>About Page (Coming Soon)</h1>"

@bp.route('/help')
def help():
    return "<h1>Help Page (Coming Soon)</h1>"