from flask import Flask, render_template, request, send_from_directory, send_file, redirect, url_for, jsonify  
import os
import boto3
import json  
from datetime import datetime  
import shutil 
import pandas as pd
from io import BytesIO
from werkzeug.utils import secure_filename
# Ensure a default AWS region is set before importing modules that create clients
boto3.setup_default_session(region_name=os.getenv('AWS_REGION', 'ap-south-1'))

from modules.models import process_pptx
from modules.model2 import main as generate_audio_story
from modules.ganttchart import generate_gantt_chart
from modules.utils import process_document_file
from modules.flowchart import process_user_input

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['AUDIO_FOLDER'] = 'static/audio'

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

FLOWCHART_DIR = "flowcharts"

# Login page (microsoft sso)
@app.route('/')
def login():
    print("Login page accessed")  
    return render_template('login.html')

# Home page (dashboard)
@app.route('/home')
def home():
    return render_template('index.html')

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

    # Call the utility function that does all processing & returns result and output filename
    result_text, output_filename = process_document_file(
        filepath=filepath,
        operation=operation,
        word_limit=word_limit,
        skip_pages_raw=skip_pages_raw,
        upload_folder=app.config['UPLOAD_FOLDER']
    )

    # --- Log the task here ---
    output_filepath = os.path.join(app.config['UPLOAD_FOLDER'], output_filename) if output_filename else None

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
