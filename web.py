#Standard Lib
#import random
import os
from functools import wraps
#from datetime import datetime, timedelta

#Third Party

from flask import Flask, render_template, request, session, redirect, url_for, send_from_directory
from flask_sqlalchemy import SQLAlchemy
#from pytz import utc
#from discord_webhook import DiscordWebhook, DiscordEmbed

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


#Discord webhook functionality cut for better system in the future
#Here we define the webhook
#webhook = DiscordWebhook(url="webhook here", username="ASMARA 2FA", avatar_url="https://github.com/A-c0rN/ASMARA/blob/main/assets/asmara-logo-only.png?raw=true")



#Define Flask and COnfiguration
app = Flask(__name__, template_folder='templates')
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql://username:password@localhost/asmara' #Change this!
db = SQLAlchemy(app)


# Load or generate the secret key
app.secret_key = load_or_generate_secret_key()


if app.secret_key == 'your_secret_key':
    new_secret_key = os.urandom(128)
    print(new_secret_key)

#Make Database Model
class users(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    password = db.Column(db.String(50))


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


#login.html route
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = users.query.filter_by(username=username).first()
        if user and user.password == password:
            # Generate a six-digit random code
            #code = str(random.randint(100000, 999999))
            # Send this code to a specific channel in your Discord server
            #send_discord_message(code)
            # Store the code and its expiration time in the session
            #session['code'] = {'value': code, 'expires_at': datetime.now(utc) + timedelta(seconds=30)}
            # Store the username in the session
            session['logged_in'] = True
            session['username'] = username
            return redirect(url_for('home'))
        else:
            return 'Invalid credentials', 401
    else:
        return render_template('login.html')
    
#extend session route, for when you go AFK on index.html
@app.route('/extend_session', methods=['POST'])
def extend_session():
    return '', 204
    
#2FA Route
#@app.route('/verify_code', methods=['GET', 'POST'])
#def verify_code():
    # Check if the code exists in the session
#    if 'code' not in session:
#        return '401 Unauthorized, Invalid Code, or you are trying to hack me!', 401

#    if request.method == 'POST':
#        entered_code = request.form.get('code')
#        code_info = session.get('code')
#        if code_info and entered_code == code_info['value'] and datetime.now(utc) <= code_info['expires_at']:
#            session['logged_in'] = True
#            # Clear the session variable holding the verification code
#            session.pop('code', None)
#            return redirect(url_for('home'))
#        else:
#            # Clear the session variable holding the verification code
#            session.pop('code', None)
#            return redirect(url_for('verify_code'))
#    else:
#        # Retrieve the flashed message from the session and store it in the template context
#        return render_template('verify_code.html')


#Logout Route
@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))


#Discord 2FA Embed
#def send_discord_message(content):
#  embed = DiscordEmbed(title="2FA Code Requested", description="Code: " + str(content) + " If you didn't request this code, its safe to ignore this message..", color="03b2f8")
#  embed.set_author(name="ASMARA")
#  embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/907457287864590396/907757517751332914/warning.png")
#  embed.set_footer(text="Code Invalid After 30 Seconds | ASMARA © 2024 MSNGTXTRS SOFT.")
#  webhook.add_embed(embed)
#  webhook.execute()

if __name__ == '__main__':
    app.run(debug=True)