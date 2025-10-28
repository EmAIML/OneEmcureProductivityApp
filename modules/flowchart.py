import boto3
import json
import graphviz
import os
from datetime import datetime

# Directory to store all flowcharts
FLOWCHART_DIR = "flowcharts"
HISTORY_FILE = "last_flowchart.json"

# Ensure directory exists
os.makedirs(FLOWCHART_DIR, exist_ok=True)

bedrock = boto3.client('bedrock-runtime', region_name='ap-south-1')

def call_haiku(prompt: str):
    try:
        response = bedrock.invoke_model(
            modelId="anthropic.claude-3-haiku-20240307-v1:0",
            contentType="application/json",
            accept="application/json",
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "messages": [
                    {"role": "user", "content": prompt}
                ],
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
    return text  # fallback if braces not found

def parse_haiku_output(output_text):
    print("🔍 Raw model output:", repr(output_text))  # debug print to see raw output
    json_str = extract_json_from_response(output_text)
    try:
        return json.loads(json_str)
    except Exception as e:
        print("Error parsing JSON:", e)
        print("JSON substring tried:", repr(json_str))
        return None

def generate_flowchart(data, filename_base):
    dot = graphviz.Digraph(format='jpg')
    dot.attr(rankdir='TB')  # vertical layout

    nodes = data.get("nodes", {})
    edges = data.get("edges", [])

    # Convert nodes list to dict if needed
    if isinstance(nodes, list):
        try:
            nodes = {
                node["id"]: {
                    k: v for k, v in node.items() if k != "id"
                } for node in nodes
            }
        except Exception as e:
            print("Error converting nodes list to dict:", e)
            return

    # Ensure Start and End nodes exist
    start_nodes = [nid for nid, node in nodes.items() if node.get('label', '').lower() == 'start']
    if not start_nodes:
        nodes["start"] = {"label": "Start", "type": "process"}
    end_nodes = [nid for nid, node in nodes.items() if node.get('label', '').lower() == 'end']
    if not end_nodes:
        nodes["end"] = {"label": "End", "type": "process"}

    # Collect decision node IDs for edge label logic
    decision_nodes = {nid for nid, node in nodes.items() if node.get("type") == "decision"}

    # Add nodes to flowchart with correct shapes
    for node_id, node_info in nodes.items():
        label = node_info.get("label", node_id)
        node_type = node_info.get("type", "process")

        if node_type == "decision":
            dot.node(node_id, label, shape="diamond", style="filled", fillcolor="lightyellow")
        elif label.lower() in ("start", "end"):
            # We'll handle the End node in a special subgraph for rank=sink below
            if label.lower() == "start":
                dot.node(node_id, label, shape="oval", style="filled", fillcolor="lightblue")
            # Skip adding End node here to add it in subgraph later
        else:
            dot.node(node_id, label, shape="box")

    # Add End node in a subgraph with rank=sink to push it to the bottom
    with dot.subgraph() as s:
        s.attr(rank='sink')
        for node_id, node_info in nodes.items():
            label = node_info.get("label", node_id)
            if label.lower() == "end":
                s.node(node_id, label, shape="oval", style="filled", fillcolor="lightblue")

    # Add edges; only label edges from decision nodes
    for edge in edges:
        from_node = edge["from"]
        to_node = edge["to"]
        label = edge.get("label", "")

        # Show edge label only if from_node is decision node and label exists
        if from_node in decision_nodes and label:
            dot.edge(from_node, to_node, label=label)
        else:
            dot.edge(from_node, to_node)

    # Save image
    output_path = dot.render(filename=filename_base, cleanup=False)
    return output_path



def load_last_flowchart():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r") as f:
            return json.load(f)
    return None

def save_flowchart_history(data):
    with open(HISTORY_FILE, "w") as f:
        json.dump(data, f, indent=2)

def save_flowchart_permanently(data, filename_base):
    # Save JSON to permanent storage
    json_path = f"{filename_base}.json"
    with open(json_path, "w") as f:
        json.dump(data, f, indent=2)

def process_user_input(user_query: str):
    from datetime import datetime

    # Create unique filename base using timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename_base = os.path.join(FLOWCHART_DIR, f"flowchart_{timestamp}")

    last_flowchart = load_last_flowchart()

    if last_flowchart:
        prompt = f"""
You are a flowchart generator that can update an existing flowchart based on new user instructions.

Here is the current flowchart JSON:
{json.dumps(last_flowchart)}

User wants to update it with this request:
"{user_query}"

Return the updated flowchart JSON with nodes and edges.
Make sure Start and End nodes remain.
Only return the JSON object.
"""
    else:
        prompt = f"""
You are a flowchart generator. Extract a step-by-step flowchart from the following user request.
Return **ONLY** a JSON object with:
- nodes: dictionary with node IDs as keys and values with "label" and "type" ("process" or "decision")
- edges: list of objects with "from", "to", and optional "label" for edge text (e.g. 'Yes' or 'No')

Include Start and End nodes.

User request: "{user_query}"

Do not include any explanation, markdown, or additional text. Only return the JSON.
"""

    haiku_text = call_haiku(prompt)
    if not haiku_text:
        return None, None, "Model did not return any response."

    data = parse_haiku_output(haiku_text)
    if not data:
        return None, None, "Failed to parse the model's response."

    # Save JSON
    save_flowchart_history(data)
    save_flowchart_permanently(data, filename_base)

    # Generate image
    image_path = generate_flowchart(data, filename_base)
    if not image_path:
        return None, None, "Failed to generate flowchart image."

    return image_path, f"{filename_base}.json", None

