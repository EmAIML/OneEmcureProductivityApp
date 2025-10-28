import os
import re
import json
import base64
import boto3
from pptx import Presentation
from botocore.exceptions import ClientError
from pptx2txt2 import extract_images 
from modules.model2 import main as generate_audio_story

# AWS Bedrock setup
client = boto3.client("bedrock-runtime", region_name="ap-south-1")
MODEL_ID = "anthropic.claude-3-haiku-20240307-v1:0"

def encode_image_to_base64(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")

def describe_image(image_base64, context_text):
    prompt = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1024,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": image_base64,
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            f"Based on the slide context: \"{context_text}\", "
                            "describe the visual content of this image. "
                            "Explain what the image likely represents within the slide topic. "
                            "Focus only on visual educational content. Avoid extra links or styling references."
                        )
                    }
                ],
            }
        ],
    }
    body = json.dumps(prompt)
    response = client.invoke_model(modelId=MODEL_ID, body=body)
    data = json.loads(response["body"].read())
    return data["content"][0]["text"]

def clean_text(text):
    text = re.sub(r'https?://\S+', '', text)
    patterns = [
        r'\bstyle\.visibility\b',
        r'\bppt_x\b',
        r'\bppt_y\b',
        r'\bstyle\.visibility\s+\S+',
        r'\bppt_x\s+\S+',
        r'\bppt_y\s+\S+',
    ]
    for pattern in patterns:
        text = re.sub(pattern, '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def extract_text_from_presentation(pptx_path):
    prs = Presentation(pptx_path)
    slide_texts = {}
    for idx, slide in enumerate(prs.slides, start=1):
        slide_text = ""
        for shape in slide.shapes:
            if hasattr(shape, "text"):
                slide_text += shape.text + "\n"
        slide_texts[idx] = clean_text(slide_text)
    return slide_texts

def process_pptx(pptx_path, output_txt_path, images_output_dir):
    os.makedirs(images_output_dir, exist_ok=True)

    # Extract text using pptx library
    slide_text_map = extract_text_from_presentation(pptx_path)

    # Extract images
    image_paths = extract_images(pptx_path, images_output_dir)

    # Map images to slides
    slide_images_map = {}
    for img_file in sorted(os.listdir(images_output_dir)):
        if img_file.startswith("slide_"):
            parts = img_file.split("_")
            if len(parts) >= 2 and parts[1].isdigit():
                slide_num = int(parts[1])
                slide_images_map.setdefault(slide_num, []).append(img_file)

    # Write output
    with open(output_txt_path, "w", encoding="utf-8") as outf:
        for slide_idx in sorted(slide_text_map.keys()):
            cleaned_text = slide_text_map[slide_idx]
            outf.write(f"\n--- Slide {slide_idx} Text ---\n")
            outf.write(cleaned_text + "\n")

            # Images for slide
            images_for_slide = slide_images_map.get(slide_idx, [])
            for img_file in images_for_slide:
                img_path = os.path.join(images_output_dir, img_file)
                try:
                    image_base64 = encode_image_to_base64(img_path)
                    description = describe_image(image_base64, cleaned_text)
                except (ClientError, Exception) as e:
                    description = f"ERROR describing image: {e}"
                outf.write(f"\nImage: {img_file}\n")
                outf.write("Description:\n" + description + "\n")

    print(f"\n Processing complete! Output written to: {output_txt_path}")

if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("Usage: python main.py input.pptx")
        sys.exit(1)

    pptx_file = sys.argv[1]

    # Get absolute path of the current script (project folder)
    project_dir = os.path.dirname(os.path.abspath(__file__))

    # Build full paths to output within the project folder
    pptx_basename = os.path.splitext(os.path.basename(pptx_file))[0]
    output_txt = os.path.join(project_dir, f"{pptx_basename}_output.txt")
    images_dir = os.path.join(project_dir, f"{pptx_basename}_images")

    process_pptx(pptx_file, output_txt, images_dir)

    generate_audio_story(output_txt, pause_ms=1500)