#Standard Lib
#import random
import os
from functools import wraps
#from datetime import datetime, timedelta

#Third Party
import pyotp
from flask import Flask, render_template, request, session, redirect, url_for, send_from_directory, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.sql.expression import desc, func
from flask_statistics import Statistics


def load_or_generate_secret_key(filename='secret_key.txt'):
    try:
        with open(filename, 'r') as file:
            secret_key = file.read().strip()
            # Check if the file is empty
            if not secret_key:
                raise FileNotFoundError
    except FileNotFoundError:
        # Generate a new 128-character secret key
        secret_key = os.urandom(128).hex()
        with open(filename, 'w') as file:
            file.write(secret_key)
    return secret_key





#Define Flask and Configuration
app = Flask(__name__, template_folder='templates')
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql://username:password@localhost/asmara' #Change this!
db = SQLAlchemy(app)


# Load or generate the secret key
app.secret_key = load_or_generate_secret_key()


if app.secret_key == 'your_secret_key':
    new_secret_key = os.urandom(128)
    print(new_secret_key)


class Request(db.Model):
    __tablename__ = "request"

    index = db.Column(db.Integer, primary_key=True, autoincrement=True)
    response_time = db.Column(db.Float)
    date = db.Column(db.DateTime)
    method = db.Column(db.String)
    size = db.Column(db.Integer)
    status_code = db.Column(db.Integer)
    path = db.Column(db.String)
    user_agent = db.Column(db.String)
    remote_address = db.Column(db.String)
    exception = db.Column(db.String)
    referrer = db.Column(db.String)
    browser = db.Column(db.String)
    platform = db.Column(db.String)
    mimetype = db.Column(db.String)

statistics = Statistics(app, db, Request)

#Make Database Model
class users(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    password = db.Column(db.String(50))
    secret = db.Column(db.String(100)) # New column for the OTP secret key


#Define the @ you put infront of a route if login is required
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


@app.route('/assets/<path:filename>')
def serve_public_file(filename):
    return send_from_directory('assets', filename)

@app.route('/favicon.ico')
def favicon():
    return send_from_directory('assets', 'favicon.ico', mimetype='image/vnd.microsoft.icon')

#index.html route
@app.route('/')
@login_required
def home():
    username = session.get('username', '')
    return render_template('index.html', username=username)


@app.route('/api/statistics')
def api_statistics():
    # Total active users
    total_users = users.query.count()
    
    # Peak response time
    peak_response_time = Request.query.with_entities(func.max(Request.response_time)).scalar()
    
    # Number of exceptions
    exceptions = Request.query.filter(Request.exception != None).count()
    
    # Exception breakdown
    exception_types = Request.query.with_entities(Request.exception).filter(Request.exception != None).group_by(Request.exception).all()
    exception_breakdown = {}
    for exc in exception_types:
        count = Request.query.filter(Request.exception == exc.exception).count()
        exception_breakdown[exc.exception] = count

    
    # Request breakdown
    request_methods = Request.query.with_entities(Request.method).group_by(Request.method).all()
    request_breakdown = {method.method: request_methods.count(method) for method in request_methods}
    
    # Response status breakdown
    response_statuses = Request.query.with_entities(Request.status_code).group_by(Request.status_code).all()
    response_status_breakdown = {status.status_code: response_statuses.count(status) for status in response_statuses}
    

    
    stats = {
        'User Accounts': total_users,
        'Peak Response Time': peak_response_time,
        'Errors': exceptions,
        'Error Breakdown': exception_breakdown,
        'Request Breakdown': request_breakdown,
        'Response Breakdown': response_status_breakdown,
    }
    
    return jsonify(stats)

#login.html route
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = users.query.filter_by(username=username).first()
        if user and user.password == password:
            # Redirect to OTP verification page
            return redirect(url_for('verify_code', username=username))
        else:
            flash('Invalid credentials')
            return redirect(url_for('login'))
    else:
        return render_template('login.html')
    
#extend session route, for when you go AFK on index.html
@app.route('/extend_session', methods=['POST'])
def extend_session():
    return '', 204
    
#2FA Route
@app.route('/verify_code', methods=['GET', 'POST'])
def verify_code():
    if request.method == 'POST':
        username = request.args.get('username')
        user_totp_code = request.form.get('code')
        user = users.query.filter_by(username=username).first()
        
        if user:
            totp = pyotp.TOTP(user.secret)
            if totp.verify(user_totp_code):
                session['logged_in'] = True
                session['username'] = username
                return redirect(url_for('home'))
            else:
                flash('Invalid OTP code')
                return redirect(url_for('verify_code', username=username))
        else:
            flash('User not found')
            return redirect(url_for('login'))
    else:
        return render_template('verify_code.html')


#Logout Route
@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)