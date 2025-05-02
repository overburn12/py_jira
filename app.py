from flask import Flask, flash, make_response, session, redirect, url_for, render_template, request, jsonify, Response
from werkzeug.security import check_password_hash
from functools import wraps
from dotenv import load_dotenv
import os, json

import py_jira

app = Flask(__name__)

#--------------------------------------------------------------------------------------
# environment variables / constants
#--------------------------------------------------------------------------------------

load_dotenv()
PORT = os.getenv('PORT')
DEBUG = os.getenv('DEBUG', False)
app.secret_key = os.getenv('SECRET_KEY')
ADMIN_NAME = os.getenv('ADMIN_NAME')
ADMIN_PASSWORD_HASH = os.getenv('ADMIN_PASSWORD_HASH')

app.config.update(
    SESSION_COOKIE_SECURE=True,    # Only send cookies over HTTPS
    SESSION_COOKIE_HTTPONLY=True,  # Prevent JavaScript from reading the cookie
    SESSION_COOKIE_SAMESITE='Strict', # Or 'Strict' if you want hardcore CSRF defense
)


#--------------------------------------------------------------------------------------
# Helpers
#--------------------------------------------------------------------------------------

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('logged_in'):
            return f(*args, **kwargs)
        else:
            flash('You need to be logged in to view this page.')
            return redirect(url_for('admin_login'))
    return decorated_function


def generate_csrf_token():
    if '_csrf_token' not in session:
        import secrets
        session['_csrf_token'] = secrets.token_hex(16)
    return session['_csrf_token']


app.jinja_env.globals['csrf_token'] = generate_csrf_token

def validate_csrf_token():
    token = session.pop('_csrf_token', None)
    form_token = request.form.get('_csrf_token')
    if not token or token != form_token:
        flash('Invalid CSRF token. Please try again.')
        return False
    return True


#--------------------------------------------------------------------------------------
# Routes
#--------------------------------------------------------------------------------------

@app.route('/', methods=['GET'])
@admin_required
def index():
    return render_template('index.html')


@app.route('/login', methods=['GET', 'POST'])
def admin_login():
    if 'logged_in' in session and session['logged_in']:
        return redirect(url_for('index'))

    if request.method == 'POST':
        if not validate_csrf_token():
            return redirect(url_for('admin_login'))

        username = request.form['username']
        password = request.form['password']
        if username == ADMIN_NAME and check_password_hash(ADMIN_PASSWORD_HASH, password):
            session['logged_in'] = True
            response = make_response(redirect(url_for('index')))
            return response
        else:
            flash('Invalid credentials')
    return render_template('admin_login.html') 


@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('admin_login'))


#--------------------------------------------------------------------------------------
# API Routes
#--------------------------------------------------------------------------------------

@app.route('/orders')
@admin_required
def get_orders():
    try:
        jira_obj = py_jira.connect_jira()
        epic_list = py_jira.get_all_rt_epics(jira_obj)
        return jsonify(epic_list)
    except Exception as e:
        app.logger.error(f"Error in /orders: {e}")
        return jsonify({"error": "Internal server error"}), 500
    

@app.route('/api', methods=['POST'])
@admin_required
def api():
    try:
        rt_number = request.json['rt_number']

        def generate_data():
            jira_obj = py_jira.connect_jira()

            for raw_hb in py_jira.get_hashboards_from_epic(jira_obj, rt_number):
                yield json.dumps(py_jira.filter_single_result(raw_hb), default=str) + '\n'

        return Response(generate_data(), mimetype='application/x-ndjson')

    except Exception as e:
        app.logger.error(f"Error in /api: {e}")
        return jsonify({"error": "Internal server error"}), 500


#--------------------------------------------------------------------------------------

@app.route('/favicon.ico')
def favicon():
    return app.send_static_file('favicon.ico')


@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404


#--------------------------------------------------------------------------------------

if __name__ == '__main__':
    app.run(host ='::', port=PORT, debug=DEBUG)