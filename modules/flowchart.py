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
    import graphviz

    dot = graphviz.Digraph(format='jpg')
    dot.attr(rankdir='TB')  # Vertical layout (Top -> Bottom)

    nodes = data.get("nodes", {})
    edges = data.get("edges", [])

    # Convert list of nodes to dict if needed
    if isinstance(nodes, list):
        try:
            nodes = {node["id"]: {k: v for k, v in node.items() if k != "id"} for node in nodes}
        except Exception as e:
            print(f"Error converting nodes list to dict: {e}")
            return None

    decision_nodes = {nid for nid, node in nodes.items() if node.get("type") == "decision"}
    end_node_ids = {nid for nid, node in nodes.items() if node.get("type") == "end" or node.get("label", "").lower() == "end"}

    # --- Shape map ---
    shape_map = {
        "start": "oval",
        "end": "oval",
        "input": "parallelogram",
        "output": "parallelogram",
        "decision": "diamond",
        "process": "box",
        "subroutine": "cds"
    }

    # --- Add nodes ---
    for node_id, node_info in nodes.items():
        label = node_info.get("label", node_id)
        node_type = node_info.get("type", "process").lower()
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

    # --- Add edges ---
    for i, edge in enumerate(edges):
        from_node = edge.get("from") or edge.get("source")
        to_node = edge.get("to") or edge.get("target")
        label = edge.get("label", "")

        if not from_node or not to_node:
            print(f"⚠️ Skipping malformed edge at index {i}: {edge}")
            continue

        # Label only decision edges
        if from_node in decision_nodes and label:
            dot.edge(from_node, to_node, label=label)
        else:
            dot.edge(from_node, to_node)

    # --- Save output ---
    try:
        output_path = dot.render(filename=filename_base, cleanup=True)
        return output_path
    except Exception as e:
        print(f"Error rendering flowchart with Graphviz: {e}")
        return None



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
        # <<< PROMPT FOR UPDATING AN EXISTING FLOWCHART >>>
        prompt = f"""
You are an intelligent **Flowchart Editor**.  
Your task is to update an existing process flowchart JSON based on a user's request, without changing unrelated logic.

---
### Current Flowchart

---
### User Request
"{user_query}"

---
### Editing Guidelines

1. Identify whether the user wants to **add**, **remove**, or **modify** steps (nodes) or transitions (edges).
2. Modify only the requested parts. Do not alter any other part of the flowchart.
3. When adding new nodes:
   * Use correct `"type"` values: `start`, `end`, `process`, `decision`, `input`, `output`, or `subroutine`.
   * Use meaningful `"label"` values (e.g., `"Check if Sum > 100"`).
   * Maintain proper **Yes/No labels** for all decision edges and where ever required and specified.
4. Ensure:
   * Flowchart has one `"start"` and at least one `"end"` node.
   * All edges connect valid node IDs.
   * Logical flow and decision labels are preserved.
5. Return **only** the updated flowchart JSON (no text or explanation).

---
Now output the updated JSON flowchart:
"""
    else:
        # <<< PROMPT FOR CREATING A NEW FLOWCHART >>>
        prompt = f"""
You are an expert **Flowchart Generator**.  
Your job is to create a **clear, complete, and properly labeled flowchart** in JSON format for the process described below.
Every start/end node → use oval/ellipse.

Every input/output → use parallelogram.

Every action or computation → use rectangle.

Every conditional check → use diamond and label outgoing edges with "Yes"/"No" (or similar).

Every subroutine → use rounded rectangle.
---
### User Request
"{user_query}"

---
### Step 1: Input Validation
If the input is unclear, incomplete, or nonsensical (e.g., random letters, a single vague word, or no actionable steps):
Return only: "The provided data is unclear. Please provide a clear description."
{{"error": "Invalid or incomplete input. Please provide a clear, step-by-step description of the process."}}
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

