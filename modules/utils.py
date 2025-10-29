import os
import uuid
import PyPDF2
import docx
import openpyxl
from pptx import Presentation
import boto3
import json
from pdf2image import convert_from_path
import pytesseract
from PIL import Image
import io


# ✅ Full path to Tesseract executable
pytesseract.pytesseract.tesseract_cmd = r'C:\Users\10028512\AppData\Local\Programs\Tesseract-OCR\tesseract.exe'

# ✅ Set environment variable to the folder CONTAINING the `tessdata` folder (with trailing backslash)
os.environ['TESSDATA_PREFIX'] = r'C:\Users\10028512\AppData\Local\Programs\Tesseract-OCR\\'
 
def extract_text_from_file(filepath, skip_pages=None):
    ext = os.path.splitext(filepath)[1].lower()
    if ext == '.pdf':
        return extract_text_from_pdf(filepath, skip_pages=skip_pages)
    elif ext in ['.docx', '.doc']:
        return extract_text_from_word(filepath, skip_pages=skip_pages)
    elif ext in ['.xlsx']:
        return extract_text_from_excel(filepath, skip_pages=skip_pages)
    elif ext in ['.txt']:
        return extract_text_from_txt(filepath, skip_pages=skip_pages)
    elif ext in ['.pptx']:
        return extract_text_from_ppt(filepath, skip_pages=skip_pages)
    else:
        return "Unsupported file type."


def extract_text_from_pdf(filepath, skip_pages=None):
    skip_pages = skip_pages or []
    text = ''
    all_pages_empty = True  # Track if all pages are non-textual

    with open(filepath, 'rb') as file:
        reader = PyPDF2.PdfReader(file)
        num_pages = len(reader.pages)

        for i, page in enumerate(reader.pages):
            if i in skip_pages:
                continue
            page_text = page.extract_text()
            if page_text and page_text.strip():
                all_pages_empty = False
                text += page_text + '\n'
            else:
                # If the page is empty, try OCR on this page
                images = convert_from_path(filepath, first_page=i+1, last_page=i+1)
                if images:
                    ocr_text = pytesseract.image_to_string(images[0])
                    text += ocr_text + '\n'

    # If every page was empty (scanned), use OCR on the entire PDF as a fallback
    if all_pages_empty:
        print("[INFO] No extractable text found, using OCR for all pages.")
        images = convert_from_path(filepath)
        text = ''
        for i, image in enumerate(images):
            if i in skip_pages:
                continue
            ocr_text = pytesseract.image_to_string(image, lang='eng')
            text += ocr_text + '\n'

    return text



def extract_text_from_word(filepath, skip_pages=None):
    skip_pages = skip_pages or []
    doc = docx.Document(filepath)
    text = ''
    paragraphs = doc.paragraphs
    # Treat paragraphs as "pages" here: For example, 20 paragraphs = 1 page
    paragraphs_per_page = 20
    total_pages = (len(paragraphs) + paragraphs_per_page - 1) // paragraphs_per_page

    for page_num in range(total_pages):
        if page_num in skip_pages:
            continue
        start = page_num * paragraphs_per_page
        end = start + paragraphs_per_page
        for para in paragraphs[start:end]:
            text += para.text + '\n'
    return text

def extract_text_from_excel(filepath, skip_pages=None):
    skip_pages = skip_pages or []
    wb = openpyxl.load_workbook(filepath)
    text = ''
    # Treat sheets as pages; skip the specified sheets (0-based index)
    sheets = list(wb)
    for i, sheet in enumerate(sheets):
        if i in skip_pages:
            continue
        for row in sheet.iter_rows(values_only=True):
            text += ' '.join([str(cell) if cell else '' for cell in row]) + '\n'
    return text

def extract_text_from_txt(filepath, skip_pages=None):
    skip_pages = skip_pages or []
    lines_per_page = 40
    text = ''
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        total_pages = (len(lines) + lines_per_page - 1) // lines_per_page
        for page_num in range(total_pages):
            if page_num in skip_pages:
                continue
            start = page_num * lines_per_page
            end = start + lines_per_page
            text += ''.join(lines[start:end])
    return text

def extract_text_from_ppt(filepath, skip_pages=None):
    skip_pages = skip_pages or []
    prs = Presentation(filepath)
    text = ''
    for i, slide in enumerate(prs.slides):
        if i in skip_pages:
            continue
        for shape in slide.shapes:
            if hasattr(shape, "text"):
                text += shape.text + '\n'
    return text

 
def call_claude_model(prompt):
    bedrock = boto3.client('bedrock-runtime', region_name='ap-south-1')
 
    body = {
        "anthropic_version": "bedrock-2023-05-31",  # Required for Claude models
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 1000,
        "temperature": 0.5,
        "top_k": 250,
        "top_p": 1,
        "stop_sequences": []
    }
 
    response = bedrock.invoke_model(
        modelId="anthropic.claude-3-haiku-20240307-v1:0",
        body=json.dumps(body),
        contentType="application/json",
        accept="application/json"
    )
 
    result = json.loads(response['body'].read())
 
    # Claude returns a 'content' list with one dictionary
    final_text = result['content'][0]['text'].strip()  
    return final_text


def process_document_file(filepath, operation, word_limit, skip_pages_raw, upload_folder):
    """
    Main utility function to handle:
    - parsing skip pages
    - extracting text
    - building prompt
    - calling AI model
    - saving output to file
    Returns (result_text, output_filename)
    """

    # Parse skip pages if any (0-based)
    skip_pages = []
    if skip_pages_raw:
        try:
            skip_pages = [int(p.strip()) - 1 for p in skip_pages_raw.split(',') if p.strip().isdigit()]
        except ValueError:
            skip_pages = []

    # Extract text (implement your own function)
    extracted_text = extract_text_from_file(filepath, skip_pages=skip_pages if operation == 'questions' else [])

    # Build prompt
    if operation == 'summary':
        prompt = f"Please summarize the following content in around {word_limit} words:\n\n{extracted_text}"
    else:
        prompt = f"""
Generate multiple choice questions based on the following content:

Content:
{extracted_text}

Instructions:
- Generate 5–10 multiple choice questions (MCQs).
- Each question should have exactly 4 options: A, B, C, and D.
- Only 1 option should be correct.
- The other 3 options should be incorrect but plausible and related to the topic.
- After each question, indicate the correct answer.
- Also provide a **1-line explanation** for why the correct answer is right.
- Format the explanation like: "Explanation: ..."

Format:
Question 1:
What is the ...?

A. Option 1  
B. Option 2  
C. Option 3  
D. Option 4  
Correct Answer: B  
Explanation: This is correct because ...
Continue in the same format.
"""

    # Call AI model
    response = call_claude_model(prompt)

    # Save result to file
    output_filename = f"{operation}_{uuid.uuid4().hex[:8]}.txt"
    output_path = os.path.join(upload_folder, output_filename)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(response)

    return response, output_filename


