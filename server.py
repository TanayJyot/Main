from flask import Flask, request, send_from_directory, jsonify
from flask_cors import CORS
import os
import subprocess
import json
from youtube_transcript_api import YouTubeTranscriptApi
from urllib.parse import urlparse, parse_qs

app = Flask(__name__)
CORS(app)

UPLOAD_FOLDER = './captions'
VIDEO_FOLDER = './videos'

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(VIDEO_FOLDER, exist_ok=True)

def extract_video_id(youtube_url: str):
    parsed_url = urlparse(youtube_url)
    if parsed_url.netloc == "youtu.be":
        return parsed_url.path.lstrip("/")
    if "youtube.com" in parsed_url.netloc:
        query_params = parse_qs(parsed_url.query)
        return query_params.get("v", [None])[0]
    return None

def fetch_captions(video_id: str):
    try:
        transcript = YouTubeTranscriptApi.get_transcript(video_id)
        return transcript
    except Exception as e:
        print(f"Failed to fetch captions: {e}")
        return []

def generate_video_from_text(text: str, output_name: str):
    """
    Call your main.sh script, passing the text, and output to a specific filename.
    """
    try:
        command = f"/bin/bash /home/ellie/GitHub/ASLytics-RBC/main.sh \"{text}\" \"{output_name}\""
        print(f"Running command: {command}")
        subprocess.run(command, shell=True, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error running main.sh: {e}")

@app.route('/upload_captions', methods=['POST'])
def upload_captions():
    data = request.get_json()
    youtube_url = data.get('url')

    if not youtube_url:
        return jsonify({'error': 'No YouTube URL received'}), 400

    video_id = extract_video_id(youtube_url)
    if not video_id:
        return jsonify({'error': 'Invalid YouTube URL'}), 400

    transcript = fetch_captions(video_id)
    if not transcript:
        return jsonify({'error': 'No captions found'}), 404

    # 清空舊資料
    for f in os.listdir(VIDEO_FOLDER):
        os.remove(os.path.join(VIDEO_FOLDER, f))

    mapping = []
    for idx, entry in enumerate(transcript):
        start_time = entry['start']
        text = entry['text'].replace('"', "'")  # 防止bash指令錯亂

        output_name = f"sentence_{idx+1}.mp4"
        output_path = os.path.join(VIDEO_FOLDER, output_name)

        # Run main.sh 產生影片
        generate_video_from_text(text, output_path)

        # 記錄 start-end對應的影片
        if idx < len(transcript) - 1:
            end_time = transcript[idx + 1]['start']
        else:
            end_time = start_time + 5.0  # 最後一個自己加個 5 秒

        mapping.append({
            "start": start_time,
            "end": end_time,
            "file": output_name
        })

    # 存一份 mapping.json
    with open(os.path.join(VIDEO_FOLDER, "mapping.json"), "w", encoding="utf-8") as f:
        json.dump(mapping, f, indent=2)

    return jsonify({'status': 'Captions processed and videos generated!'})

@app.route('/videos', methods=['GET'])
def list_videos():
    files = os.listdir(VIDEO_FOLDER)
    video_files = [f for f in files if f.endswith('.mp4')]
    return jsonify({'videos': video_files})

@app.route('/mapping', methods=['GET'])
def get_mapping():
    with open(os.path.join(VIDEO_FOLDER, "mapping.json"), "r", encoding="utf-8") as f:
        mapping = json.load(f)
    return jsonify(mapping)

@app.route('/video/<filename>', methods=['GET'])
def get_video(filename):
    return send_from_directory(VIDEO_FOLDER, filename)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
