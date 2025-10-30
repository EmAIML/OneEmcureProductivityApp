import os
import base64
import boto3
import json
import time
from PIL import Image
from pdf2image import convert_from_path
from botocore.exceptions import ClientError
from docx import Document

# === SETTINGS ===
OUTPUT_FILE = "generated_result.txt"

# === UTILITY FUNCTIONS ===

def pdf_to_images(pdf_path):
    print("Converting PDF pages to images...")
    return convert_from_path(pdf_path, dpi=300)

def extract_text_from_image(image_path, max_retries=5):
    print(f"Extracting text from image: {image_path}")
    client = boto3.client("bedrock-runtime", region_name="ap-south-1")

    image = Image.open(image_path)
    max_width = 1024
    if image.width > max_width:
        w_percent = max_width / float(image.width)
        h_size = int(float(image.height) * w_percent)
        image = image.resize((max_width, h_size), Image.LANCZOS)
        image.save(image_path)

    with open(image_path, "rb") as f:
        image_bytes = f.read()
    base64_image = base64.b64encode(image_bytes).decode("utf-8")

    prompt_text = (
        "Extract only the relevant and meaningful content (not title, headers, or footers) "
        "from this image. Do not summarize. Just output the plain clean text."
    )

    payload = {
        "anthropic_version": "bedrock-2023-05-31",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": base64_image}},
                    {"type": "text", "text": prompt_text},
                ],
            }
        ],
        "max_tokens": 8000,
    }

    retries = 0
    while retries < max_retries:
        try:
            response = client.invoke_model(
                modelId="anthropic.claude-3-haiku-20240307-v1:0",
                contentType="application/json",
                accept="application/json",
                body=json.dumps(payload).encode("utf-8"),
            )

            result_json = json.loads(response["body"].read().decode("utf-8"))
            clean_text = ""
            for item in result_json.get("content", []):
                if item["type"] == "text":
                    clean_text += item["text"]

            return clean_text.strip()

        except ClientError as e:
            if e.response["Error"]["Code"] == "ThrottlingException":
                wait_time = 2 ** retries
                print(f"⚠️ Throttled. Waiting {wait_time}s before retrying... (Attempt {retries + 1})")
                time.sleep(wait_time)
                retries += 1
            else:
                raise
        except Exception as e:
            print(f"Unexpected error: {e}")
            raise

    raise Exception("Max retries reached. Giving up.")

def extract_text_and_images_from_docx(docx_path):
    print(f"Extracting text and images from Word file: {docx_path}")
    doc = Document(docx_path)
    full_text = ""

    # Extract paragraph text
    for para in doc.paragraphs:
        if para.text.strip():
            full_text += para.text + "\n"

    # Extract embedded images safely
    image_counter = 1
    for rel in doc.part._rels.values():
        if "image" in rel.reltype and getattr(rel, "target_part", None):
            image_bytes = rel.target_part.blob
            image_path = f"docx_image_{image_counter}.png"
            with open(image_path, "wb") as f:
                f.write(image_bytes)
            print(f"Extracting text from embedded image: {image_path}")

            try:
                image_text = extract_text_from_image(image_path)
                full_text += f"\n\n--- Image {image_counter} ---\n{image_text}"
                image_counter += 1
            except Exception as e:
                print(f"Error extracting text from image {image_path}: {e}")
            finally:
                os.remove(image_path)

    return full_text

def generate_summary_from_text(text, word_limit=100, max_retries=5):
    print(f"Generating summary (limit {word_limit} words)...")
    prompt_text = f"Summarize the following text in at most {word_limit} words. Focus on the main content and keep it concise:\n\n{text}"

    client = boto3.client("bedrock-runtime", region_name="ap-south-1")
    payload = {
        "anthropic_version": "bedrock-2023-05-31",
        "messages": [{"role": "user", "content": [{"type": "text", "text": prompt_text}]}],
        "max_tokens": 3000,
    }

    retries = 0
    while retries < max_retries:
        try:
            response = client.invoke_model(
                modelId="anthropic.claude-3-haiku-20240307-v1:0",
                contentType="application/json",
                accept="application/json",
                body=json.dumps(payload).encode("utf-8"),
            )

            result_json = json.loads(response["body"].read().decode("utf-8"))
            summary = ""
            for item in result_json.get("content", []):
                if item["type"] == "text":
                    summary += item["text"]

            return summary.strip()

        except ClientError as e:
            if e.response["Error"]["Code"] == "ThrottlingException":
                wait_time = 2 ** retries
                print(f"⚠️ Throttled. Waiting {wait_time}s before retrying... (Attempt {retries + 1})")
                time.sleep(wait_time)
                retries += 1
            else:
                raise
        except Exception as e:
            print(f"Unexpected error while generating summary: {e}")
            raise

    raise Exception("Max retries reached while generating summary.")

def generate_mcqs_from_text(text, max_retries=5):
    print("Generating MCQs from extracted text...")
    prompt_text = (
        "Based only on the following text, generate exactly 40 high-quality, fact-based multiple choice questions.\n\n"
        "Use this strict format:\n"
        "Q1. <Question>\n"
        "A. <Option A>\n"
        "B. <Option B>\n"
        "C. <Option C>\n"
        "D. <Option D>\n"
        "Correct Answer: <A/B/C/D>\n"
        "Explanation: <Short explanation>\n\n"
        "Rules:\n"
        "- Do NOT make up any information not present in the text.\n"
        "- Only generate questions that are clearly answerable from the content.\n"
        "- Ensure no duplicate or overly similar questions.\n"
        "- All questions must be factual.\n"
        "- Only one correct option per question.\n"
    )

    client = boto3.client("bedrock-runtime", region_name="ap-south-1")
    payload = {
        "anthropic_version": "bedrock-2023-05-31",
        "messages": [{"role": "user", "content": [{"type": "text", "text": prompt_text + "\n\nText Content:\n" + text}]}],
        "max_tokens": 8000,
    }

    retries = 0
    while retries < max_retries:
        try:
            response = client.invoke_model(
                modelId="anthropic.claude-3-haiku-20240307-v1:0",
                contentType="application/json",
                accept="application/json",
                body=json.dumps(payload).encode("utf-8"),
            )

            result_json = json.loads(response["body"].read().decode("utf-8"))
            mcqs = ""
            for item in result_json.get("content", []):
                if item["type"] == "text":
                    mcqs += item["text"]

            return mcqs.strip()

        except ClientError as e:
            if e.response["Error"]["Code"] == "ThrottlingException":
                wait_time = 2 ** retries
                print(f"⚠️ Throttled. Waiting {wait_time}s before retrying... (Attempt {retries + 1})")
                time.sleep(wait_time)
                retries += 1
            else:
                raise
        except Exception as e:
            print(f"Unexpected error while generating MCQs: {e}")
            raise

    raise Exception("Max retries reached while generating MCQs.")

def process_document(input_path, operation="summary", word_limit=100, pages_to_skip=[]):
    ext = os.path.splitext(input_path)[1].lower()
    combined_text = ""

    if ext == ".pdf":
        images = pdf_to_images(input_path)
        for i, image in enumerate(images):
            page_number = i + 1
            if page_number in pages_to_skip:
                print(f"Skipping Page {page_number}")
                continue

            image_path = f"page_{page_number}.png"
            image.save(image_path)

            try:
                page_text = extract_text_from_image(image_path)
                combined_text += f"\n\n--- Page {page_number} ---\n{page_text}"
                print(f"Text extracted from Page {page_number}")
                time.sleep(1)
            except Exception as e:
                print(f"Error on page {page_number}: {e}")

            os.remove(image_path)

    elif ext == ".docx":
        combined_text = extract_text_and_images_from_docx(input_path)

    else:
        raise Exception("Unsupported file type. Please provide PDF or Word (.docx).")

    if not combined_text.strip():
        raise Exception("No content extracted from document.")

    if operation == "summary":
        return generate_summary_from_text(combined_text, word_limit=word_limit)
    elif operation == "questions":
        return generate_mcqs_from_text(combined_text)
    else:
        raise Exception("Invalid operation selected. Choose 'summary' or 'questions'.")
