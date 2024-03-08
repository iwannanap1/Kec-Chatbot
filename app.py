from flask import Flask, jsonify, render_template, request, redirect, session, url_for, flash
import json 
import numpy as np
import tensorflow as tf
from sklearn.preprocessing import LabelEncoder
import random
import pickle
from fuzzywuzzy import fuzz 
import mysql.connector
from functools import wraps
import requests
from flask_mysqldb import MySQL
from datetime import datetime

MAX_LEN = 20

def load_model_paths(language):
    base_path = '/Users/Shrijana/majorproject1/'
    data_path = f'{base_path}{language}response.json'
    model_path = f'{base_path}{language}/model1'
    tokenizer_path = f'{base_path}{language}/tokenizer1.pickle'
    label_encoder_path = f'{base_path}{language}/label_encoder1.pickle'
    return data_path, model_path, tokenizer_path, label_encoder_path

def load_model(data_path, model_path, tokenizer_path, label_encoder_path):
    with open(data_path, encoding='utf-8') as file:
        response = json.load(file)

    model = tf.keras.models.load_model(model_path)

    with open(tokenizer_path, 'rb') as handle:
        tokenizer = pickle.load(handle)

    with open(label_encoder_path, 'rb') as enc:
        label_encoder = pickle.load(enc)

    return response, model, tokenizer, label_encoder

# Load English model at startup
english_model_paths = load_model_paths('english')
english_response, english_model, english_tokenizer, english_label_encoder = load_model(*english_model_paths)

# Load Nepali model at startup
nepali_model_paths = load_model_paths('nepali')
nepali_response, nepali_model, nepali_tokenizer, nepali_label_encoder = load_model(*nepali_model_paths)


def get_response(user_inp, language='english'):
    if language == 'english':
        response, model, tokenizer, label_encoder = english_response, english_model, english_tokenizer, english_label_encoder
    elif language == 'nepali':
        response, model, tokenizer, label_encoder = nepali_response, nepali_model, nepali_tokenizer, nepali_label_encoder
    else:
        return {'response': 'Unsupported language'}

    if 'upcoming events' in user_inp:
        upcoming_events = get_upcoming_events()
        if upcoming_events:
            # If there are upcoming events, prepare the response
            response_text = "Upcoming events: \n"
            for event in upcoming_events:
                # name, date, location, details = event
                name = event['name']
                date = event['date']
                venue = event['venue']
                details = event['details']
                response_text += f"- Name:{name}\n Date:{date}\n Location:{venue}\n Details:{details}\n"
            # Return the response
            return {'response_type': 'text', 'response': response_text}
        else:
            # If there are no upcoming events, return a message indicating so
            return {'response_type': 'text', 'response': "No upcoming events found."}
    else:
        result = model.predict(tf.keras.preprocessing.sequence.pad_sequences(tokenizer.texts_to_sequences([user_inp]),
                                             truncating='post', maxlen=MAX_LEN), verbose=0)
    
        if np.max(result) > 0.2:
            tag = label_encoder.inverse_transform([np.argmax(result)])
        else:
            tag = ['error']

        # Best response selection
        best_match = tag[0] if tag else 'error'
        best_response = response.get(best_match, 'error')

        if 'table' in best_response:
            return {'response_type': 'table', 'response': best_response['table'],'text': best_response['text']}
        elif 'url' in best_response:
            return {'response_type': 'image', 'response': best_response['url'],'text': best_response['text']}
        else:
            return {'response_type': 'text', 'response': best_response, 'text': ''}


app = Flask(__name__)
app.secret_key = 'aabnvgashyghauwuwa'

# Define admin credentials
ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = 'admin'

# mysql = MySQL(app)

# Initialize MySQL connection
db_connection = mysql.connector.connect(
    host="localhost",
    user="root",
    password="shrijana",
    database="chatbot"
)

# Initialize cursor
db_cursor = db_connection.cursor(dictionary=True)  # Set dictionary=True to fetch rows as dictionaries

def admin_login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if 'admin_logged_in' in session:
            return func(*args, **kwargs)
        else:
            return redirect(url_for('login'))
    return wrapper

@app.route('/events', methods=['GET', 'POST'])
@admin_login_required
def events():
    if request.method == 'POST':
        try:
            # Check if cursor is connected, if not, reconnect
            if not db_connection.is_connected():
                db_connection.reconnect()

            # Reinitialize cursor
            db_cursor = db_connection.cursor(dictionary=True)
            # Fetch form data
            details = request.form
            name = details['name']
            date = details['date']
            venue = details['venue']
            event_details = details['details']

            # Store data in MySQL database
            db_cursor.execute("INSERT INTO events(name, date, venue, details) VALUES(%s, %s, %s, %s)",
                              (name, date, venue, event_details))
            db_connection.commit()
        except mysql.connector.Error as err:
            print("MySQL Error:", err)

    try:
        # Check if cursor is connected, if not, reconnect
        if not db_connection.is_connected():
            db_connection.reconnect()
        # Reinitialize cursor
        db_cursor = db_connection.cursor(dictionary=True)
        # Fetch events from the database
        db_cursor.execute("SELECT * FROM events")
        events = db_cursor.fetchall()
        return render_template('events.html', events=events)
    except mysql.connector.Error as err:
        print("MySQL Error:", err)
        return render_template('events.html', events=[])
    finally:
        db_cursor.close()




@app.route('/display_events')
@admin_login_required
def display_events():
    try:
        # Check if cursor is connected, if not, reconnect
        if not db_connection.is_connected():
            db_connection.reconnect()

        # Reinitialize cursor
        db_cursor = db_connection.cursor(dictionary=True)

        # Fetch events from the database
        db_cursor.execute("SELECT * FROM events")
        events = db_cursor.fetchall()
        return render_template('display_events.html', events=events)
    except mysql.connector.Error as err:
        print("MySQL Error:", err)
        return "An error occurred while fetching events. Please try again later."
    finally:
        db_cursor.close()


@app.route('/delete_event', methods=['POST'])
@admin_login_required
def delete_event():
    try:
        # Get event ID from the form submission
        event_id = request.form.get('event_id')

        # Delete event from the database
        db_cursor.execute("DELETE FROM events WHERE id = %s", (event_id,))
        db_connection.commit()

        return redirect('/display_events')  # Redirect to the events page after deletion
    except mysql.connector.Error as err:
        print("MySQL Error:", err)
        return "An error occurred while deleting the event. Please try again later."

@app.route('/edit_event', methods=['POST'])
@admin_login_required
def edit_event():
    try:
        # Get event ID from the form submission
        event_id = request.form.get('event_id')

        # Fetch event details from the database
        db_cursor.execute("SELECT * FROM events WHERE id = %s", (event_id,))
        event = db_cursor.fetchone()

        return render_template('edit_event.html', event=event)  # Render edit form with event details
    except mysql.connector.Error as err:
        print("MySQL Error:", err)
        return "An error occurred while fetching event details. Please try again later."
          
@app.route('/update_event', methods=['POST'])
@admin_login_required
def update_event():
    try:
        # Get event ID and updated details from the form submission
        event_id = request.form.get('event_id')
        name = request.form.get('name')
        date = request.form.get('date')
        venue = request.form.get('venue')
        details = request.form.get('details')

        # Check if required fields are not empty
        if not name:
            flash("Name cannot be empty", "error")
            return redirect('/display_events')  # Redirect back to the events page without updating

        # Update event details in the database
        db_cursor.execute("UPDATE events SET name = %s, date = %s, venue = %s, details = %s WHERE id = %s",
                          (name, date, venue, details, event_id))
        db_connection.commit()

        return redirect('/display_events')  # Redirect to the events page after updating
    except mysql.connector.Error as err:
        print("MySQL Error:", err)
        return "An error occurred while updating the event. Please try again later."

def get_upcoming_events():
    try:
        # Connect to MySQL database
        connection = mysql.connector.connect(
            host="localhost",
            user="root",
            password="shrijana",
            database="chatbot"
        )
        
        if connection.is_connected():
            cursor = connection.cursor(dictionary=True)
            
            # Query upcoming events from database
            query = "SELECT name,CAST(date AS DATETIME) AS event_date, venue, details FROM events WHERE date > %s ORDER BY date ASC"
            current_time = datetime.now()
            print("Current Time:", current_time)
            cursor.execute(query, (current_time,))
            events = cursor.fetchall()

            # Print out fetched events
            for event in events:
                print(event)
            
            # Format events for display
            event_list = []
            for event in events:
                event_info = {
                    'name': event['name'],
                    'date': event['event_date'],
                    'venue': event['venue'],
                    'details': event['details']
                }
                event_list.append(event_info)
                print(event_info)
                print(event_list)
                print(type(event_info['date']))  
            
            return event_list
    
    except mysql.connector.Error as e:
        print("Error connecting to MySQL database:", e)
    
    finally:
        # Close database connection
        if connection.is_connected():
            cursor.close()
            connection.close()



def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if 'logged_in' in session:
            return func(*args, **kwargs)
        else:
            return redirect('/')
    return wrapper

@app.route('/')
def home():
    if 'logged_in' in session:
        return redirect(url_for('index'))  # Redirect regular users to a different page
    elif 'admin_logged_in' in session:
        return redirect(url_for('admin_dashboard'))  # Redirect admins to a different page
    return render_template('login.html')


@app.route('/login', methods=['POST'])
def login():
    try:
        username = request.form['username']
        password = request.form['password']

        # Check if the user is an admin
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['admin_logged_in'] = True
            session['username'] = username
            return redirect(url_for('admin_dashboard'))

        # Query the database for the user
        db_cursor.execute("SELECT * FROM users WHERE username = %s AND password = %s", (username, password))
        user = db_cursor.fetchone()

        if user:
            session['logged_in'] = True
            session['username'] = username
            return redirect('/index')
        else:
            return 'Invalid login'
    except mysql.connector.Error as err:
        print("MySQL Error:", err)
        return 'An error occurred while processing your request'
    
@app.route('/admin/dashboard')
@admin_login_required
def admin_dashboard():
    if 'admin_logged_in' in session:
        return render_template('dashboard.html')
    else:
        return redirect(url_for('login'))

    
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    try:
        if request.method == 'POST':
            username = request.form['username']
            email = request.form['email']
            password = request.form['password']

            # Check if username already exists
            db_cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
            existing_user = db_cursor.fetchone()
            if existing_user:
                return 'Username already exists'

            # Insert new user into the database
            db_cursor.execute("INSERT INTO users (username,email, password) VALUES (%s, %s, %s)", (username, email, password))
            db_connection.commit()

            session['logged_in'] = True
            session['username'] = username
            return redirect('/index')
        else:
            return render_template('login.html')
    except mysql.connector.Error as err:
        print("MySQL Error:", err)
        return 'An error occurred while processing your request'
    
@app.route('/index')
@login_required 
def index():
    return render_template('index.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/') 

def user_or_admin_login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if 'logged_in' in session or 'admin_logged_in' in session:
            return func(*args, **kwargs)
        else:
            return redirect(url_for('login'))
    return wrapper

@app.route('/englishchat.html')
@user_or_admin_login_required
def enghome():
    user_input = request.args.get('user_input', '')  # Retrieve user input from the request
    user_response = get_response(user_input, language="english")
    return render_template('englishchat.html', response=user_response)


@app.route('/nepalichat.html')
@user_or_admin_login_required
def nephome():
    user_input = request.args.get('user_input', '')  # Retrieve user input from the request
    user_response = get_response(user_input, language="nepali")
    return render_template('nepalichat.html', response = user_response)

@app.route("/get")
def get_bot_response():
    userText = request.args.get('msg')
    language = request.args.get('lang', 'english')  # Default to English if language is not provided
    response = get_response(userText, language)
    # chat_message = get_response(userText, language)  # Assuming get_response returns a dictionary
    return jsonify(response)
    # return chat_message

if __name__ == '__main__':
    app.run(port=5000)