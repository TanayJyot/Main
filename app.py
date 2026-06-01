from flask import Flask, request, render_template, jsonify
from flask_cors import CORS
import subprocess
import os
from utils.youtube_caption_utils import extract_video_id, get_youtube_captions_with_timing
from merge_asl_clips import merge_asl_video_clips

app = Flask(__name__)
CORS(app)
app.config['UPLOAD_FOLDER'] = 'static/videos'

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        youtube_url = request.form['youtube_url']
        video_id = extract_video_id(youtube_url)

        if not video_id:
            return "Invalid YouTube URL."

        # extract captions, with start, duration, text
        captions = get_youtube_captions_with_timing(video_id)

        if not captions:
            return "No captions available for this video."

        # ensure static/videos exists
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

        generated_files = []

        # generate clips
        for idx, cap in enumerate(captions):  
            sentence = cap['text']
            if not sentence.strip() or sentence.strip().startswith('['):
                print(f"Skipping empty or non-verbal caption: {sentence}")
                continue

            filename = f"caption_{idx}.mp4"
            output_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

            result = subprocess.run(
                ["bash", "utils/generate_asl_video.sh", sentence, output_path],
                capture_output=True,
                text=True
            )

            print("STDOUT:", result.stdout)
            print("STDERR:", result.stderr)

            if os.path.exists(output_path):
                generated_files.append(filename)
            else:
                print(f"Failed to generate video for sentence: {sentence}")

        if not generated_files:
            return "No ASL videos were generated."

        # calculates the length of the video
        last_caption = captions[-1]
        total_duration = last_caption['start'] + last_caption['duration']

        # combine clips
        merge_asl_video_clips(
            video_dir=app.config['UPLOAD_FOLDER'],
            captions_with_time=captions[:len(generated_files)],
            output_path="static/final_asl_output.mp4",
            total_duration=total_duration
        )

        return render_template('index.html',
                               youtube_url=youtube_url,
                               final_asl_video="final_asl_output.mp4")

    return render_template('index.html')

@app.route('/process', methods=['POST'])
def process_caption_api():

    data = request.json

    caption = data.get("caption", "")

    print("Received caption:", caption)

    # TEMP TEST
    asl_translation = caption.upper()

    return jsonify({
        "asl_translation": asl_translation
    })


if __name__ == "__main__":
    app.run(debug=True)
