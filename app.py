from flask import Flask, render_template, request, send_from_directory, send_file, redirect, url_for, jsonify, session
from authlib.integrations.flask_client import OAuth 
import os
import secrets
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
import matplotlib
matplotlib.use('Agg')  
import matplotlib.pyplot as plt
from modules.utils import process_document
from modules.flowchart import process_user_input
boto3.setup_default_session(region_name=os.getenv('AWS_REGION', 'ap-south-1'))

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['AUDIO_FOLDER'] = 'static/audio'
app.config['OUTPUT_FOLDER'] = 'static/output'
app.config['EXCEL_OUTPUT_FOLDER'] = 'static/output/excels'
app.config['GANTT_IMAGE_FOLDER'] = 'static/output/images'


os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)
os.makedirs(app.config['EXCEL_OUTPUT_FOLDER'], exist_ok=True)
os.makedirs(app.config['GANTT_IMAGE_FOLDER'], exist_ok=True)

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

#  This must match EXACTLY your Azure Redirect URI
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
def login():
    # Microsoft will redirect back to this route after login
    if 'code' in request.args:
        token = microsoft.authorize_access_token()

        #  Pass the nonce used during authorization
        nonce = session.pop('nonce', None)
        user_info = microsoft.parse_id_token(token, nonce=nonce)

        if user_info:
            session['user'] = user_info
            print("User logged in:", user_info)
            return redirect(url_for('home'))
        return "Authorization failed", 400
    
    # Otherwise show login page
    return render_template('login.html')


@app.route('/login')
def login_route():
    # Generate and store nonce for ID token validation
    nonce = secrets.token_urlsafe(16)
    session['nonce'] = nonce

    redirect_uri = app.config['MICROSOFT_REDIRECT_URI']
    return microsoft.authorize_redirect(redirect_uri, nonce=nonce)


@app.route('/home')
def home():
    if "user" not in session:
        return redirect(url_for("login_route"))
    
    user = session["user"]
    name = user.get("name", "User")
    email = user.get("preferred_username", user.get("email", ""))

    return render_template('index.html', name=name, email=email)

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
    audio_file = session.pop('audio_file', None)
    return render_template('ppt-to-mp3.html', audio_file=audio_file)

@app.route('/upload', methods=['POST'])
def upload_ppt_to_mp3():

    if 'ppt_file' not in request.files:
        return redirect(url_for('ppt_to_mp3'))

    file = request.files['ppt_file']
    if file.filename == '':
        return redirect(url_for('ppt_to_mp3'))

    filename = secure_filename(file.filename)
    ppt_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(ppt_path)

    base_name = os.path.splitext(filename)[0]
    txt_output_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{base_name}_output.txt")
    images_output_dir = os.path.join(app.config['UPLOAD_FOLDER'], f"{base_name}_images")

    # ---- PROCESS STARTS ----
    process_pptx(ppt_path, txt_output_path, images_output_dir)
    generate_audio_story(txt_output_path, pause_ms=1500)

    audio_filename = f"{base_name}_audio.mp3"
    temp_audio_path = os.path.join('static', 'audio', 'story_audio.mp3')
    final_audio_path = os.path.join(app.config['AUDIO_FOLDER'], audio_filename)

    if os.path.exists(temp_audio_path):
        shutil.move(temp_audio_path, final_audio_path)
    else:
        session['audio_file'] = None
        return redirect(url_for('ppt_to_mp3'))

    # ---- STORE RESULT & REDIRECT ----
    session['audio_file'] = audio_filename
    return redirect(url_for('ppt_to_mp3'))


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
    skip_pages_raw = request.form.get('skip_pages', '').strip()

    filename = secure_filename(file.filename)
    ext = os.path.splitext(filename)[1].lower()

    word_extensions = [".doc",".docx",".dot",".dotx",".docm",".dotm",".xml",".rtf",".txt"]

    # Validate
    if ext not in [".pdf"] + word_extensions:
        session['doc_error'] = "Unsupported file format"
        return redirect(url_for('doc_summarizer'))

    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)

    if skip_pages_raw:
        pages_to_skip = [int(x.strip()) for x in skip_pages_raw.split(',') if x.strip().isdigit()]
    else:
        pages_to_skip = []

    try:
        result_text = process_document(
            input_path=filepath,
            operation=operation,
            pages_to_skip=pages_to_skip
        )
    except Exception as e:
        session['doc_error'] = str(e)
        return redirect(url_for('doc_summarizer'))

    output_filename = "processed_output.txt"
    output_filepath = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)
    with open(output_filepath, "w", encoding="utf-8") as f:
        f.write(result_text)

    session['doc_result'] = result_text
    session['doc_download'] = output_filename

    return redirect(url_for('doc_summarizer'))


@app.route('/doc-summarizer', methods=['GET'])
def doc_summarizer():
    result = session.pop('doc_result', None)
    error = session.pop('doc_error', None)
    download_file = session.pop('doc_download', None)

    return render_template(
        "doc-summarizer.html",
        result=result,
        error=error,
        download_file=download_file
    )


@app.route('/download/<filename>', endpoint='download_file')
def download_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)

# Gantt chart Generation
@app.route('/gantt-chart', methods=['GET', 'POST'])
def gantt_chart():
    if request.method == 'POST':
        file = request.files.get('file')
        if not file:
            return render_template('gantt-chart.html', error="No file uploaded")

        include_saturday = request.form.get('include_saturday', 'yes').lower() == 'yes'
        include_sunday = request.form.get('include_sunday', 'yes').lower() == 'yes'

        filename = secure_filename(file.filename)
        if filename == "":
            return render_template('gantt-chart.html', error="Invalid filename")

        # save uploaded file
        unique = secrets.token_hex(8)
        upload_name = f"{unique}_{filename}"
        upload_path = os.path.join(app.config['UPLOAD_FOLDER'], upload_name)
        file.save(upload_path)

        try:
            # generate gantt excel using module
            output_excel, meta = generate_gantt_chart(
                upload_path,
                include_saturday=include_saturday,
                include_sunday=include_sunday
            )
        except Exception as e:
            # show error on page
            return render_template('gantt-chart.html', error=str(e))

        # copy/move excel into static output for download
        excel_basename = os.path.basename(output_excel)
        excel_dest = os.path.join(app.config['EXCEL_OUTPUT_FOLDER'], f"{unique}_{excel_basename}")
        shutil.copy(output_excel, excel_dest)

        # read task list to create image
        try:
            df = pd.read_excel(output_excel, sheet_name='Task List', engine='openpyxl')
        except Exception as e:
            return render_template('gantt-chart.html', error=f"Failed reading generated excel: {e}")

        # ensure Start Date and End Date are datetime
        if not pd.api.types.is_datetime64_any_dtype(df['Start Date']):
            df['Start Date'] = pd.to_datetime(df['Start Date'], errors='coerce')
        if not pd.api.types.is_datetime64_any_dtype(df['End Date']):
            df['End Date'] = pd.to_datetime(df['End Date'], errors='coerce')

        # build plot
        plt.figure(figsize=(12, max(4, 0.4 * len(df))))  # height scales with number of tasks
        # convert dates to matplotlib date numbers is optional; matplotlib handles datetimes
        y_positions = range(len(df))
        # use reversed order so first task appears at top
        for i, (idx, row) in enumerate(df.iloc[::-1].iterrows()):
            task_name = row['Task']
            start = row['Start Date']
            end = row['End Date']
            if pd.isna(start) or pd.isna(end):
                continue
            duration = (end - start).days + 1
            plt.barh(i, duration, left=start, height=0.6)

        plt.yticks(range(len(df)), df['Task'].iloc[::-1])
        plt.xlabel('Date')
        plt.title('Gantt Chart Preview')
        plt.tight_layout()

        img_name = f"gantt_{unique}.png"
        img_path = os.path.join(app.config['GANTT_IMAGE_FOLDER'], img_name)
        plt.savefig(img_path, bbox_inches='tight')
        plt.close()

        # prepare URLs for template (these are relative to static folder)
        excel_rel = f"output/excels/{os.path.basename(excel_dest)}"
        img_rel = f"output/images/{img_name}"

        return render_template('gantt-chart.html',
                               gantt_image=img_rel,
                               download_excel=excel_rel,
                               ai_summary=meta.get("ai_summary", ""),
                               open_tasks=meta.get("open_tasks", []),
                               project_start=meta.get("project_start"),
                               project_end=meta.get("project_end")
                               )

    return render_template('gantt-chart.html')

# Flow chart Generation
@app.route('/flow-chart', methods=['GET', 'POST'])
def flow_chart():
    from modules.flowchart import load_history
    return render_template("flow-chart.html", history=load_history(), prompt_value="")

@app.route("/generate", methods=["POST"])
def generate():
    from modules.flowchart import process_user_input, load_history

    user_query = request.form["process_text"]
    image_path, _, error = process_user_input(user_query)

    if error:
        session['flow_error'] = error
        return redirect("/flow-chart")

    session['flow_image'] = f"/download-image/{os.path.basename(image_path)}"
    session['flow_query'] = user_query

    return redirect("/flow-chart")


@app.route('/flow-chart')
def flow_chart():
    from modules.flowchart import load_history

    return render_template(
        "flow-chart.html",
        history=load_history(),
        image_url=session.pop('flow_image', None),
        prompt_value=session.pop('flow_query', "")
    )


@app.route("/session/<session_id>")
def load_session(session_id):
    from modules.flowchart import load_history

    history = load_history()
    item = next((x for x in history if x["id"] == session_id), None)
    
    if not item:
        return "Session not found."

    return render_template(
        "flow-chart.html",
        image_url="/" + item["image_file"],
        prompt_value=item["prompt"],
        history=history
    )

@app.route('/edit/<session_id>')
def edit_flowchart(session_id):
    from modules.flowchart import load_history
    history = load_history()

    item = next((x for x in history if x["id"] == session_id), None)

    if not item:
        return "Session not found"

    # Load JSON data
    with open(item["json_file"], "r") as f:
        json_data = json.load(f)

    return render_template(
        "edit-flowchart.html",
        flowchart=json_data,
        session_id=session_id,
        history=history
    )

@app.route("/apply-edit/<session_id>", methods=["POST"])
def apply_edit(session_id):
    from modules.flowchart import load_history, generate_flowchart, save_full_session

    history = load_history()
    item = next((x for x in history if x["id"] == session_id), None)
    if not item:
        return "Session not found"

    # Load JSON flowchart
    with open(item["json_file"], "r") as f:
        data = json.load(f)

    nodes = data["nodes"]
    edges = data["edges"]

    # ==========================
    # UPDATE EXISTING NODES
    # ==========================
    for node_id, node in nodes.items():
        new_label = request.form.get(f"label_{node_id}")
        new_type = request.form.get(f"type_{node_id}")

        if new_label:
            node["label"] = new_label
        if new_type:
            node["type"] = new_type

    # ==========================
    # ADD NEW NODE
    # ==========================
    new_node_id = request.form.get("new_node_id")
    if new_node_id:
        nodes[new_node_id] = {
            "label": request.form.get("new_node_label"),
            "type": request.form.get("new_node_type")
        }

    # ==========================
    # DELETE NODE
    # ==========================
    delete_node_id = request.form.get("delete_node_id")
    if delete_node_id and delete_node_id in nodes:
        nodes.pop(delete_node_id)
        # Remove edges referencing the node
        data["edges"] = [
            e for e in data["edges"]
            if e["from"] != delete_node_id and e["to"] != delete_node_id
        ]

    # ==========================
    # UPDATE EXISTING EDGES
    # ==========================
    edge_count = int(request.form.get("edge_count", 0))
    new_edges = []

    for i in range(edge_count):
        frm = request.form.get(f"edge_from_{i}")
        to = request.form.get(f"edge_to_{i}")
        label = request.form.get(f"edge_label_{i}")

        if frm and to:
            edge = {"from": frm, "to": to}
            if label:
                edge["label"] = label
            new_edges.append(edge)

    data["edges"] = new_edges

    # ==========================
    # ADD NEW EDGE
    # ==========================
    new_edge_from = request.form.get("new_edge_from")
    new_edge_to = request.form.get("new_edge_to")
    if new_edge_from and new_edge_to:
        new_edge = {"from": new_edge_from, "to": new_edge_to}
        label = request.form.get("new_edge_label")
        if label:
            new_edge["label"] = label
        data["edges"].append(new_edge)

    # ==========================
    # DELETE EDGE
    # ==========================
    delete_edge_expr = request.form.get("delete_edge")
    if delete_edge_expr and "→" in delete_edge_expr:
        frm, to = [x.strip() for x in delete_edge_expr.split("→")]
        data["edges"] = [
            e for e in data["edges"] if not (e["from"] == frm and e["to"] == to)
        ]

    # ==========================
    # SAVE UPDATED VERSION
    # ==========================
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename_base = f"flowcharts/flowchart_edit_{timestamp}"

    with open(f"{filename_base}.json", "w") as f:
        json.dump(data, f, indent=2)

    image_path = generate_flowchart(data, filename_base)

    save_full_session("EDIT: " + item["prompt"], data, image_path)

    return redirect("/flow-chart")



if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)
