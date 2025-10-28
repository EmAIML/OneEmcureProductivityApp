import os
import io
import sys
import json
import re
import time
import boto3
import tempfile
import subprocess
from botocore.exceptions import BotoCoreError, ClientError
import xml.sax.saxutils as saxutils

# AWS Clients
bedrock_client = boto3.client("bedrock-runtime", region_name="ap-south-1")
polly_client = boto3.client("polly")

# Configuration
MODEL_ID = "meta.llama3-70b-instruct-v1:0"
VOICE_ID = "Kajal"
MAX_POLLY_CHARS = 2900
OUTPUT_FILENAME = os.path.join("static", "audio", "story_audio.mp3")

def extract_text_from_txt(txt_path):
    with open(txt_path, "r", encoding="utf-8") as file:
        text = file.read()
    return " ".join(text.split())

def convert_to_story(text, max_gen_len=512, temp=0.1, top_p=0.9, max_retries=3):
    instruction = (
        "Rewrite the following slide content into a polished, concise story format. "
        "Do NOT include any extra commentary such as 'Here is a rewritten version...' or similar phrases. "
        "Only output the story text directly.\n\n"
    )
    for attempt in range(1, max_retries + 1):
        formatted_prompt = (
            "<|begin_of_text|>\n"
            "<|start_header_id|>user<|end_header_id|>\n"
            f"{instruction}{text}\n"
            "<|eot_id|>\n"
            "<|start_header_id|>assistant<|end_header_id|>\n"
        )
        body = {
            "prompt": formatted_prompt,
            "max_gen_len": max_gen_len,
            "temperature": temp,
            "top_p": top_p
        }
        try:
            resp = bedrock_client.invoke_model(
                modelId=MODEL_ID,
                body=json.dumps(body),
                contentType="application/json",
                accept="application/json"
            )
            resp_body = json.loads(resp["body"].read())
            gen = resp_body.get("generation", "")
            print(f"Attempt {attempt} generation:", repr(gen))
            if gen and gen.strip():
                return gen
        except Exception as e:
            print("Bedrock invocation error:", e)
        print("Retrying prompt with different settings..." if attempt < max_retries else "All attempts failed.")
        time.sleep(1)
    return None

def enforce_slide_numbers_in_story(original_batch_text, generated_story):
    original_slide_numbers = re.findall(r"Slide\s*(\d+)", original_batch_text)
    story_paragraphs = re.split(r'\n\s*\n', generated_story.strip())

    corrected_paragraphs = []
    for idx, para in enumerate(story_paragraphs):
        if idx < len(original_slide_numbers):
            slide_number = original_slide_numbers[idx]
            if not para.strip().lower().startswith(f"slide {slide_number}"):
                para = f"Slide {slide_number}: {para.strip()}"
        corrected_paragraphs.append(para.strip())

    return "\n\n".join(corrected_paragraphs)

def add_ssml_tags(text, pause_duration_ms=3000):
    def insert_slide_breaks_before(txt):
        pattern = re.compile(r'\b(Slide\s*\d+:)', flags=re.IGNORECASE)
        return pattern.sub(lambda m: f'<break time="{pause_duration_ms}ms"/>{m.group(1)}', txt)

    text_with_slide_breaks = insert_slide_breaks_before(text)

    parts = re.split(r'(<break time="\d+ms"/>)', text_with_slide_breaks)
    escaped_parts = []
    for part in parts:
        if part.startswith('<break'):
            escaped_parts.append(part)
        else:
            escaped_parts.append(saxutils.escape(part))

    text_with_breaks_and_escapes = ''.join(escaped_parts)

    def insert_punctuation_breaks(txt):
        pieces = re.split(r'(<break time="\d+ms"/>)', txt)
        new_pieces = []
        for piece in pieces:
            if piece.startswith('<break'):
                new_pieces.append(piece)
            else:
                piece = re.sub(r'([,:.;!?])(?!<break)', r'\1<break time="300ms"/>', piece)
                new_pieces.append(piece)
        return ''.join(new_pieces)

    final_ssml_text = insert_punctuation_breaks(text_with_breaks_and_escapes)

    ssml = f'<speak><prosody rate="80%">{final_ssml_text}</prosody></speak>'
    return ssml

def synthesize_text_chunk_to_file(text, index, output_dir):
    try:
        response = polly_client.synthesize_speech(
            Text=text,
            TextType="ssml",
            OutputFormat="mp3",
            VoiceId=VOICE_ID,
            Engine="neural"
        )
        if "AudioStream" in response:
            filename = os.path.join(output_dir, f"chunk_{index}.mp3")
            with open(filename, "wb") as f:
                f.write(response["AudioStream"].read())
            return filename
        else:
            print(f"[Error] Polly response missing audio stream for chunk {index}.")
            return None
    except (BotoCoreError, ClientError) as e:
        print(f"[Error] Polly failed for chunk {index}: {e}")
        return None

def generate_transition_audio(output_dir, voice_id=VOICE_ID):
    text = "<speak>Let's move to next slide.</speak>"
    try:
        response = polly_client.synthesize_speech(
            Text=text,
            TextType="ssml",
            OutputFormat="mp3",
            VoiceId=voice_id,
            Engine="neural"
        )
        if "AudioStream" in response:
            filename = os.path.join(output_dir, "transition.mp3")
            with open(filename, "wb") as f:
                f.write(response["AudioStream"].read())
            return filename
        else:
            print("[Error] Polly response missing audio stream for transition.")
            return None
    except (BotoCoreError, ClientError) as e:
        print(f"[Error] Polly failed for transition audio: {e}")
        return None

def merge_audio_chunks(chunk_files, output_filename):
    output_dir = os.path.dirname(output_filename)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmpdir:
        # Generate transition audio snippet
        transition_file = generate_transition_audio(tmpdir)
        if not transition_file:
            print("Failed to generate transition audio. Merging without transitions.")
            files_to_merge = chunk_files
        else:
            files_to_merge = []
            for i, chunk in enumerate(chunk_files):
                files_to_merge.append(chunk)
                if i < len(chunk_files) - 1:
                    files_to_merge.append(transition_file)

        list_file = os.path.join(tmpdir, "chunk_list.txt")
        with open(list_file, "w", encoding="utf-8") as f:
            for chunk in files_to_merge:
                f.write(f"file '{chunk}'\n")

        command = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", list_file, "-c", "copy", output_filename
        ]

        try:
            subprocess.run(command, check=True)
            print(f"\nFinal MP3 saved: {output_filename}")
        except subprocess.CalledProcessError as e:
            print("ffmpeg merge failed:", e)
            sys.exit(1)

def split_by_slide(text):
    slides = re.split(r'\b(Slide\s*\d+)\b', text, flags=re.IGNORECASE)
    slide_contents = []
    for i in range(1, len(slides), 2):
        title = slides[i].strip()
        content = slides[i + 1].strip() if i + 1 < len(slides) else ""
        slide_contents.append(f"{title} {content}")
    return slide_contents

def group_slides(slides, batch_size=1):
    for i in range(0, len(slides), batch_size):
        yield slides[i:i + batch_size]

def main(txt_file, pause_ms=3000, max_valid_slide=44):
    if not os.path.isfile(txt_file):
        print("Text file not found:", txt_file)
        sys.exit(1)

    print("Extracting text...")
    raw_text = extract_text_from_txt(txt_file)

    print("Splitting by slide...")
    slide_sections = split_by_slide(raw_text)

    print(f"Filtering slides up to Slide {max_valid_slide}")
    valid_sections = []
    for section in slide_sections:
        match = re.search(r"Slide\s+(\d+)", section, re.IGNORECASE)
        if match and int(match.group(1)) <= max_valid_slide:
            valid_sections.append(section)
        elif not match:
            valid_sections.append(section)

    chunk_files = []
    with tempfile.TemporaryDirectory() as tempdir:
        for batch_idx, slide_batch in enumerate(group_slides(valid_sections, batch_size=1)):
            print(f"\nGenerating story for Slide {batch_idx + 1}")

            batch_text = "\n\n".join(slide_batch).strip()
            if len(batch_text.split()) < 2:
                print("Skipping short batch.")
                continue

            story = convert_to_story(batch_text)
            if not story:
                print("Retrying batch after pause...")
                time.sleep(3)
                continue

            final_story = enforce_slide_numbers_in_story(batch_text, story.strip())
            ssml = add_ssml_tags(final_story, pause_duration_ms=pause_ms)

            file_path = synthesize_text_chunk_to_file(ssml, batch_idx, tempdir)
            if file_path:
                chunk_files.append(file_path)
            else:
                print(f"[Warning] Skipping slide {batch_idx + 1} due to synthesis error.")

        if not chunk_files:
            print("No audio chunks were created.")
            sys.exit(1)

        merge_audio_chunks(chunk_files, OUTPUT_FILENAME)

if __name__ == "__main__":
    if len(sys.argv) < 2 or len(sys.argv) > 4:
        print("Usage: python generate_story_audio.py <input.txt> [pause_ms] [max_slide]")
        sys.exit(1)

    input_file = sys.argv[1]
    pause_duration = int(sys.argv[2]) if len(sys.argv) >= 3 else 3000
    max_slide_number = int(sys.argv[3]) if len(sys.argv) == 4 else 44

    main(input_file, pause_ms=pause_duration, max_valid_slide=max_slide_number)
