from flask import Blueprint, redirect, url_for, render_template

bp = Blueprint('main', __name__)

@bp.route('/')
def index():
    return redirect(url_for('main.about'))

@bp.route('/about')
def about():
    return render_template('about.html')

@bp.route('/help')
def help():
    return render_template('help.html')