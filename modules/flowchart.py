import boto3
import json
import graphviz
import os
from datetime import datetime
import shutil

# =========================
# DIRECTORIES
# =========================
FLOWCHART_DIR = "flowcharts"
HISTORY_FILE = "last_flowchart.json"

HISTORY_INDEX = "chat_history.json"
HISTORY_DIR = "static/history"

os.makedirs(FLOWCHART_DIR, exist_ok=True)
os.makedirs(HISTORY_DIR, exist_ok=True)

# AWS Client
bedrock = boto3.client('bedrock-runtime', region_name='ap-south-1')

# =========================
# CHAT HISTORY SAVE / LOAD
# =========================

def load_history():
    """Load master chat history list"""
    if os.path.exists(HISTORY_INDEX):
        with open(HISTORY_INDEX, "r") as f:
            return json.load(f)
    return []

def save_full_session(prompt, flowchart_json_data, image_path):
    """Save prompt + JSON + image into a session folder"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_id = f"session_{timestamp}"

    json_path = os.path.join(HISTORY_DIR, f"{session_id}.json")
    image_output = os.path.join(HISTORY_DIR, f"{session_id}.jpg")

    # Save JSON file
    with open(json_path, "w") as f:
        json.dump(flowchart_json_data, f, indent=2)

    # Copy image
    shutil.copy(image_path, image_output)

    # Prepare entry
    entry = {
        "id": session_id,
        "prompt": prompt,
        "json_file": json_path,
        "image_file": image_output,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    # Load, update and rewrite index
    history_list = load_history()
    history_list.insert(0, entry)

    with open(HISTORY_INDEX, "w") as f:
        json.dump(history_list, f, indent=2)

    return entry


# =========================
# MODEL CALLING
# =========================

def call_haiku(prompt: str):
    try:
        response = bedrock.invoke_model(
            modelId="anthropic.claude-3-haiku-20240307-v1:0",
            contentType="application/json",
            accept="application/json",
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 1000
            })
        )
        result = json.loads(response['body'].read().decode())
        return result['content'][0]['text']
    except Exception as e:
        print("Error calling Haiku:", e)
        return None

def extract_json_from_response(text):
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end != -1 and end > start:
        return text[start:end+1]
    return text

def parse_haiku_output(output_text):
    print(" Raw model output:", repr(output_text))
    json_str = extract_json_from_response(output_text)
    try:
        return json.loads(json_str)
    except Exception as e:
        print("Error parsing JSON:", e)
        print("JSON substring tried:", repr(json_str))
        return None

# =========================
# FLOWCHART GENERATION
# =========================

def generate_flowchart(data, filename_base):
    dot = graphviz.Digraph(format='jpg')
    dot.attr(rankdir='TB')

    nodes = data.get("nodes", {})
    edges = data.get("edges", [])

    if isinstance(nodes, list):
        nodes = {n["id"]: {k: v for k, v in n.items() if k != "id"} for n in nodes}

    decision_nodes = {nid for nid, node in nodes.items() if node.get("type") == "decision"}

    shape_map = {
        "start": "oval",
        "end": "oval",
        "input": "parallelogram",
        "output": "parallelogram",
        "decision": "diamond",
        "process": "box",
        "subroutine": "cds"
    }

    for node_id, info in nodes.items():
        label = info.get("label", node_id)
        node_type = info.get("type", "process").lower()
        shape = shape_map.get(node_type, "box")

        fillcolor = {
            "start": "#A9CCE3",
            "end": "#A9CCE3",
            "process": "#D5F5E3",
            "decision": "#F9E79F",
            "input": "#E5E5E5",
            "output": "#E5E5E5",
            "subroutine": "#D6DBDF"
        }.get(node_type, "#FFFFFF")

        dot.node(node_id, label, shape=shape, style="filled", fillcolor=fillcolor)

    for edge in edges:
        from_node = edge.get("from") or edge.get("source")
        to_node = edge.get("to") or edge.get("target")
        label = edge.get("label", "")
        if not from_node or not to_node:
            continue
        if from_node in decision_nodes and label:
            dot.edge(from_node, to_node, label=label)
        else:
            dot.edge(from_node, to_node)

    try:
        return dot.render(filename=filename_base, cleanup=True)
    except Exception as e:
        print("Graphviz Error:", e)
        return None


# =========================
# HISTORY HELPERS
# =========================

def load_last_flowchart():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r") as f:
            return json.load(f)
    return None

def save_flowchart_history(data):
    with open(HISTORY_FILE, "w") as f:
        json.dump(data, f, indent=2)

def save_flowchart_permanently(data, filename_base):
    with open(f"{filename_base}.json", "w") as f:
        json.dump(data, f, indent=2)

# =========================
# MAIN PROCESSING FUNCTION
# =========================

def process_user_input(user_query: str):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename_base = os.path.join(FLOWCHART_DIR, f"flowchart_{timestamp}")

    last_flowchart = load_last_flowchart()

    # NEW FLOWCHART PROMPT
    prompt = f"""
Create a flowchart JSON for this process:
"{user_query}"
"""

    haiku_text = call_haiku(prompt)
    if not haiku_text:
        return None, None, "Model returned no response."

    data = parse_haiku_output(haiku_text)
    if not data:
        return None, None, "Failed to parse model response."

    save_flowchart_history(data)
    save_flowchart_permanently(data, filename_base)

    image_path = generate_flowchart(data, filename_base)
    if not image_path:
        return None, None, "Failed to generate flowchart image."

    # SAVE SESSION HISTORY (NEW)
    save_full_session(user_query, data, image_path)

    return image_path, f"{filename_base}.json", None
