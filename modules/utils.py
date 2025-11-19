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
REGION = "ap-south-1"
MODEL_ID = "anthropic.claude-3-haiku-20240307-v1:0"

# === INITIALIZE BEDROCK CLIENT ===
def get_bedrock_client():
    session = boto3.session.Session()
    return session.client("bedrock-runtime", region_name=REGION)

# === UTILITIES ===
def pdf_to_images(pdf_path):
    print("Converting PDF pages to images...")
    return convert_from_path(pdf_path, dpi=200)

def extract_text_from_image(image_path, max_retries=5):
    print(f"Extracting text from image: {image_path}")
    client = get_bedrock_client()

    # Resize large images to avoid 413 error
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
        "Extract all readable and meaningful text from this image. "
        "Do not summarize; return plain text only. Ignore titles, page numbers, and headers."
    )

    payload = {
        "anthropic_version": "bedrock-2023-05-31",
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": base64_image}},
                {"type": "text", "text": prompt_text}
            ]
        }],
        "max_tokens": 8000
    }

    retries = 0
    while retries < max_retries:
        try:
            response = client.invoke_model(
                modelId=MODEL_ID,
                contentType="application/json",
                accept="application/json",
                body=json.dumps(payload).encode("utf-8"),
            )
            result_json = json.loads(response["body"].read().decode("utf-8"))
            final_text = "".join(
                [c["text"] for c in result_json.get("content", []) if c["type"] == "text"]
            ).strip()

            if not final_text.strip():
                print("⚠ OCR returned empty text.")

            return final_text

        except ClientError as e:
            if e.response["Error"]["Code"] == "ThrottlingException":
                wait = 2 ** retries
                print(f"Throttled. Retrying in {wait}s...")
                time.sleep(wait)
                retries += 1
            else:
                raise
        except Exception as e:
            print(f"Unexpected error: {e}")
            retries += 1
            time.sleep(2)

    raise Exception("Max retries reached. Image text extraction failed.")

def extract_text_and_images_from_docx(docx_path):
    print(f"Extracting text and images from Word file: {docx_path}")
    doc = Document(docx_path)
    full_text = ""

    # Extract paragraphs
    for para in doc.paragraphs:
        if para.text.strip():
            full_text += para.text + "\n"

    # Extract images
    img_count = 1
    for rel in doc.part._rels.values():
        if "image" in rel.reltype and getattr(rel, "target_part", None):
            img_bytes = rel.target_part.blob
            img_path = f"docx_image_{img_count}.png"
            with open(img_path, "wb") as f:
                f.write(img_bytes)

            try:
                img_text = extract_text_from_image(img_path)
                if img_text.strip():
                    full_text += f"\n\n--- Image {img_count} ---\n{img_text}"
                else:
                    print(f"⚠ No OCR text extracted from image {img_count}")

            except Exception as e:
                print(f"Error extracting text from image: {e}")

            finally:
                os.remove(img_path)

            img_count += 1

    if not full_text.strip():
        print("⚠ DOCX contains no readable text or images.")

    return full_text

def chunk_text(text, max_length=12000):
    return [text[i:i+max_length] for i in range(0, len(text), max_length)]

def generate_summary_from_text(text):
    print("Generating intelligent summary...")
    client = get_bedrock_client()

    text_chunks = chunk_text(text)
    combined_summary = ""

    for idx, chunk in enumerate(text_chunks, 1):
        print(f"Processing summary chunk {idx}/{len(text_chunks)}...")
        prompt = (
            "You are an expert summarizer. Write a detailed summary of the text below "
            "while preserving all important facts and context. No meta info.\n\nText:\n" + chunk
        )

        payload = {
            "anthropic_version": "bedrock-2023-05-31",
            "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
            "max_tokens": 8000,
        }

        retries = 0
        while retries < 5:
            try:
                response = client.invoke_model(
                    modelId=MODEL_ID,
                    contentType="application/json",
                    accept="application/json",
                    body=json.dumps(payload).encode("utf-8"),
                )
                result_json = json.loads(response["body"].read().decode("utf-8"))
                summary_chunk = "".join(
                    [c["text"] for c in result_json.get("content", []) if c["type"] == "text"]
                )
                combined_summary += summary_chunk.strip() + "\n\n"
                break
            except Exception as e:
                print(f"Retrying summary chunk {idx} due to error: {e}")
                time.sleep(2 ** retries)
                retries += 1

    return combined_summary.strip()

def generate_mcqs_from_text(text):
    print("Generating MCQs...")
    client = get_bedrock_client()
    text_chunks = chunk_text(text, max_length=10000)
    all_mcqs = ""

    for idx, chunk in enumerate(text_chunks, 1):
        print(f"Processing MCQ chunk {idx}/{len(text_chunks)}...")
        prompt = (
            "From the text below, generate 40 MCQs in this format:\n\n"
            "Q1. <Question>\nA. <Option A>\nB. <Option B>\nC. <Option C>\nD. <Option D>\n"
            "Correct Answer: <A/B/C/D>\nExplanation: <Short explanation>\n\n"
            "Rules:\n- Use only information from the text.\n- No duplicates.\n\n"
            "Text:\n" + chunk
        )

        payload = {
            "anthropic_version": "bedrock-2023-05-31",
            "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
            "max_tokens": 8000,
        }

        retries = 0
        while retries < 5:
            try:
                response = client.invoke_model(
                    modelId=MODEL_ID,
                    contentType="application/json",
                    accept="application/json",
                    body=json.dumps(payload).encode("utf-8"),
                )
                result_json = json.loads(response["body"].read().decode("utf-8"))
                mcqs = "".join(
                    [c["text"] for c in result_json.get("content", []) if c["type"] == "text"]
                )
                all_mcqs += mcqs.strip() + "\n\n"
                break
            except Exception as e:
                print(f"Retrying MCQ chunk {idx} due to error: {e}")
                time.sleep(2 ** retries)
                retries += 1

    return all_mcqs.strip()

def process_document(input_path, operation="summary", pages_to_skip=None):
    if pages_to_skip is None:
        pages_to_skip = []

    ext = os.path.splitext(input_path)[1].lower()
    word_extensions = [
    ".doc", ".docx", ".dot", ".dotx", ".docm", ".dotm",
    ".xml", ".rtf", ".txt"
    ]

    if ext not in [".pdf"] + word_extensions:
        return {"error": "Unsupported file format! Only PDF and Word documents are allowed."}



    combined_text = ""

    if ext == ".pdf":
        images = pdf_to_images(input_path)
        for i, image in enumerate(images):
            page_num = i + 1
            if page_num in pages_to_skip:
                print(f"Skipping Page {page_num}")
                continue

            img_path = f"page_{page_num}.png"
            image.save(img_path)

            try:
                page_text = extract_text_from_image(img_path)
                if not page_text.strip():
                    print(f"⚠ OCR returned empty for Page {page_num}")
                combined_text += f"\n\n--- Page {page_num} ---\n{page_text}"

            except Exception as e:
                print(f"Error extracting from page {page_num}: {e}")

            finally:
                os.remove(img_path)

    elif ext == ".docx":
        combined_text = extract_text_and_images_from_docx(input_path)

    # === SAFETY CHECK ===
    if not combined_text.strip():
        print("\n=== DEBUG: No text extracted ===")
        print("Possible reasons:")
        print("1. PDF is scanned & OCR failed")
        print("2. DOCX contains only images but OCR failed")
        print("3. Poppler missing on system (install required)")
        print("4. Images generated were empty or corrupted\n")
        raise Exception("No content extracted from document. Please verify your file or OCR setup.")

    if operation == "summary":
        return generate_summary_from_text(combined_text)
    elif operation == "questions":
        return generate_mcqs_from_text(combined_text)
    else:
        raise ValueError("Invalid operation. Choose 'summary' or 'questions'.")
