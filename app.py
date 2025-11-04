from flask import Flask, render_template, request, send_from_directory, send_file, redirect, url_for, jsonify, session
from authlib.integrations.flask_client import OAuth 
import os
import boto3
import json  
from datetime import datetime  
import shutil 
import pandas as pd
from io import BytesIO
from werkzeug.utils import secure_filename
from modules.models import process_pptx
from modules.model2 import main as generate_audio_story
from modules.ganttchart import generate_gantt_chart
from modules.utils import process_document
from modules.flowchart import process_user_input
boto3.setup_default_session(region_name=os.getenv('AWS_REGION', 'ap-south-1'))

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['AUDIO_FOLDER'] = 'static/audio'

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

FLOWCHART_DIR = "flowcharts"
# #login page
# @app.route('/')
# def login():
#     print("Login page accessed")  
#     return render_template('login.html')
 
# # Home page (dashboard)
# @app.route('/home')
# def home():
#     return render_template('index.html')
app.secret_key = os.urandom(24)

# Initialize OAuth
oauth = OAuth(app)

# Microsoft OAuth Configuration
app.config['MICROSOFT_CLIENT_ID'] = 'cfa5c66e-bed1-4e03-a8b1-eb527942680c'
app.config['MICROSOFT_CLIENT_SECRET'] = 'Wdl8Q~Zu~V3~6F5_3RdC0ydgae3Ps7I0B6iW2aof'
app.config['MICROSOFT_TENANT'] = '5c1f1620-2fa8-46e0-b7f6-be5a8531bf36'
app.config['MICROSOFT_AUTHORITY'] = f"https://login.microsoftonline.com/{app.config['MICROSOFT_TENANT']}"
app.config['MICROSOFT_METADATA_URL'] = f"{app.config['MICROSOFT_AUTHORITY']}/v2.0/.well-known/openid-configuration"

# ✅ This must match EXACTLY your Azure Redirect URI
app.config['MICROSOFT_REDIRECT_URI'] = 'https://productivity.oneemcure.ai'

# Register Microsoft OAuth client
microsoft = oauth.register(
    name='microsoft',
    client_id=app.config['MICROSOFT_CLIENT_ID'],
    client_secret=app.config['MICROSOFT_CLIENT_SECRET'],
    server_metadata_url=app.config['MICROSOFT_METADATA_URL'],
    client_kwargs={'scope': 'openid email profile User.Read'},
)

# Root route — also serves as login callback
@app.route('/')
def root():
    # If user is returning from Microsoft with a code parameter
    if 'code' in request.args:
        token = microsoft.authorize_access_token()
        user_info = microsoft.parse_id_token(token)
        if user_info:
            session['user'] = user_info
            print("User logged in:", user_info)
            return redirect(url_for('home'))
        return "Authorization failed", 400
    
    # Otherwise show login page
    return render_template('login.html')

# Explicit login trigger
@app.route('/login')
def login_route():
    redirect_uri = app.config['MICROSOFT_REDIRECT_URI']
    return microsoft.authorize_redirect(redirect_uri)

# Dashboard
@app.route('/home')
def home():
    if "user" not in session:
        return redirect(url_for("login_route"))
    
    user = session["user"]
    name = user.get("name", "User")
    email = user.get("preferred_username", user.get("email", ""))
    return render_template('index.html', name=name, email=email)

# Logout
@app.route('/logout')
def logout():
    session.pop('user', None)
    logout_url = (
        f"{app.config['MICROSOFT_AUTHORITY']}/oauth2/v2.0/logout"
        f"?post_logout_redirect_uri=https://productivity.oneemcure.ai"
    )
    return redirect(logout_url)

# PPT to MP3 conversion 
@app.route('/ppt-to-mp3', methods=['GET'])
def ppt_to_mp3():
    return render_template('ppt-to-mp3.html')

# Upload PPT file and process
@app.route('/upload', methods=['POST'])
def upload_ppt_to_mp3():
    if 'ppt_file' not in request.files:
        return "No file part in request"

    file = request.files['ppt_file']
    if file.filename == '':
        return "No file selected"

    filename = secure_filename(file.filename)
    ppt_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(ppt_path)

    base_name = os.path.splitext(filename)[0]
    txt_output_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{base_name}_output.txt")
    images_output_dir = os.path.join(app.config['UPLOAD_FOLDER'], f"{base_name}_images")

    # Process PPT to text & images
    process_pptx(ppt_path, txt_output_path, images_output_dir)

    # Generate audio from the extracted text
    audio_filename = f"{base_name}_audio.mp3"
    temp_audio_path = os.path.join('static', 'audio', 'story_audio.mp3')  # model2 always writes this
    final_audio_path = os.path.join(app.config['AUDIO_FOLDER'], audio_filename)

    generate_audio_story(txt_output_path, pause_ms=1500)

    if os.path.exists(temp_audio_path):
        try:
            shutil.move(temp_audio_path, final_audio_path)
        except Exception as e:
            return f"Error moving audio file: {e}"
    else:
        return "Audio generation failed. Please try again."

    # --- Logging done ---

    return render_template('ppt-to-mp3.html', audio_file=audio_filename)

# Document Processor
@app.route('/doc-summarizer', methods=['GET', 'POST'])
def doc_summarizer():
    if request.method == 'POST':
        pass
    return render_template('doc-summarizer.html')


@app.route('/process', methods=['POST'])
def process():
    file = request.files['document']
    operation = request.form['operation']
    word_limit = request.form.get('word_limit', 100)
    skip_pages_raw = request.form.get('skip_pages', '').strip()

    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)

    # --- Convert skip_pages_raw (string) to list of ints ---
    if skip_pages_raw:
        pages_to_skip = [int(x.strip()) for x in skip_pages_raw.split(',') if x.strip().isdigit()]
    else:
        pages_to_skip = []

    # --- Call process_document correctly ---
    result_text = process_document(
        input_path=filepath,
        operation=operation,
        word_limit=int(word_limit),
        pages_to_skip=pages_to_skip
    )

    # --- Save output to a file for download ---
    output_filename = "processed_output.txt"
    output_filepath = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)
    with open(output_filepath, "w", encoding="utf-8") as f:
        f.write(result_text)

    # --- Return response to frontend ---
    return render_template('doc-summarizer.html', result=result_text, download_file=output_filename)

@app.route('/download/<filename>', endpoint='download_file')
def download_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)

# Gantt chart Generation
@app.route('/gantt-chart', methods=['GET', 'POST'])
def gantt_chart():
    if request.method == 'POST':
        # handle upload and generate gantt chart
        file = request.files['file']

        include_saturday = request.form.get('include_saturday', 'yes').lower() == 'yes'
        include_sunday = request.form.get('include_sunday', 'yes').lower() == 'yes'

        if file:
            filename = secure_filename(file.filename)
            input_path = os.path.join('uploads', filename)
            file.save(input_path)

            output_path = generate_gantt_chart(input_path,
                                              include_saturday=include_saturday,
                                              include_sunday=include_sunday)
            # --- Logging done ---
            return send_file(output_path, as_attachment=True)
       
    return render_template('gantt-chart.html')

# Flow chart Generation
@app.route('/flow-chart', methods=['GET'])
def flow_chart():
    return render_template('flow-chart.html')

@app.route("/generate", methods=["POST"])
def generate():
    user_query = request.form["process_text"]
    image_path, _, error = process_user_input(user_query)

    if error:
        return f"<h2>Error:</h2><p>{error}</p><a href='/'>Go Back</a>"

    image_filename = os.path.basename(image_path)

    # --- Logging done ---

    return render_template("flow-chart.html", image_url=f"/download-image/{image_filename}")

@app.route('/download-image/<filename>', endpoint='download_image_file')
def download_image_file(filename):
    return send_from_directory(FLOWCHART_DIR, filename, as_attachment=False)

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)
