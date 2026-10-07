from flask import Flask, request, render_template, jsonify
from flask_cors import CORS
import hashlib
import json
import os
from utils.youtube_caption_utils import extract_video_id, get_youtube_captions_with_timing
from merge_asl_clips import merge_asl_video_clips
from utils.generate_asl_video import (GenerationError, generate_with_report, lexicon_letters, lexicon_words,
                                      text_to_gloss)
from utils import aslytics_env
from showcase import tiers as showcase_tiers

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)
CORS(app)
app.config['UPLOAD_FOLDER'] = os.path.join(REPO_ROOT, 'static', 'videos')
# Videos for the sentence page. Git ignores this folder (see its .gitignore),
# so trying sentences never touches the tracked sample videos above.
SENTENCE_FOLDER = os.path.join(REPO_ROOT, 'static', 'sentences')
# Videos for the showcase page; also ignored by git. The community tier uses
# sources we may use for non-commercial purposes only (showcase/sources.py,
# DATA_LICENSES.md).
SHOWCASE_FOLDER = os.path.join(REPO_ROOT, 'static', 'showcase')


def sign_credit():
    """Where the signs come from, from the lexicon's lexicon.json if it has one.

    PopSign is CC BY 4.0, which requires crediting it wherever its signs are
    shown; popsign_lexicon.py writes this file for that reason.
    """
    manifest = aslytics_env.lexicon_dir() / "lexicon.json"
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return {"source": data.get("source", ""), "license": data.get("license", "")}


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

            # Called in-process rather than through bash: on Windows, `bash`
            # from Python can resolve to WSL's, which cannot see the venv.
            try:
                report = generate_with_report(sentence, output_path)
                if report["spelled"]:
                    print(f"  fingerspelled: {' '.join(report['spelled'])}")
                if report["skipped"]:
                    print(f"  skipped (no sign in the lexicon): {' '.join(report['skipped'])}")
            except GenerationError as error:
                print(f"Failed to generate video for sentence: {sentence}\n  {error}")
                continue

            # Carry the caption's own timing with its file. Rebuilding the
            # pairing later from list positions breaks as soon as one
            # caption is skipped above.
            generated_files.append(dict(cap, file=filename))

        if not generated_files:
            return "No ASL videos were generated."

        # calculates the length of the video
        last_caption = captions[-1]
        total_duration = last_caption['start'] + last_caption['duration']

        # combine clips
        merge_asl_video_clips(
            video_dir=app.config['UPLOAD_FOLDER'],
            captions_with_time=generated_files,
            output_path=os.path.join(REPO_ROOT, "static", "final_asl_output.mp4"),
            total_duration=total_duration
        )

        return render_template('index.html',
                               youtube_url=youtube_url,
                               final_asl_video="final_asl_output.mp4",
                               credit=sign_credit())

    return render_template('index.html', credit=sign_credit())


@app.route('/sentence', methods=['GET', 'POST'])
def sentence_page():
    """Type a sentence, get the signs. The quickest way to try a lexicon."""
    words = lexicon_words()
    context = {"words": words, "letters": lexicon_letters(), "credit": sign_credit()}
    sentence = request.form.get('sentence', '').strip() if request.method == 'POST' else ''
    if not sentence:
        return render_template('sentence.html', **context)

    context["sentence"] = sentence
    os.makedirs(SENTENCE_FOLDER, exist_ok=True)
    filename = hashlib.sha1(sentence.encode("utf-8")).hexdigest()[:16] + ".mp4"
    try:
        report = generate_with_report(sentence, filename, skip_missing=True,
                                      publish_dir=SENTENCE_FOLDER)
        context.update(video=f"sentences/{filename}", signed=report["glosses"],
                       spelled=report["spelled"], skipped=report["skipped"])
    except GenerationError as error:
        context["error"] = str(error)
    return render_template('sentence.html', **context)

@app.route('/showcase', methods=['GET', 'POST'])
def showcase_page():
    """One sentence, signed by each lexicon side by side (showcase/tiers.py)."""
    tiers = showcase_tiers.tiers()
    context = {"tiers": tiers, "examples": showcase_tiers.SENTENCES,
               "restricted": any(tier.non_commercial for tier in tiers)}
    sentence = request.form.get('sentence', '').strip() if request.method == 'POST' else ''
    if not sentence or not tiers:
        return render_template('showcase.html', **context)

    context["sentence"] = sentence
    try:
        glosses = text_to_gloss(sentence)
    except GenerationError as error:
        context["error"] = str(error)
        return render_template('showcase.html', **context)
    context["glosses"] = glosses
    os.makedirs(SHOWCASE_FOLDER, exist_ok=True)
    stem = hashlib.sha1(sentence.encode("utf-8")).hexdigest()[:16]
    results = []
    for tier in tiers:
        result = {"tier": tier, "signed": [], "spelled": [], "skipped": [], "video": None}
        if glosses:
            try:
                report = generate_with_report(sentence, f"{stem}_{tier.slug}.mp4", glosses=glosses,
                                              skip_missing=True, publish_dir=SHOWCASE_FOLDER,
                                              lexicon_dir=tier.path)
                result.update(signed=report["glosses"], spelled=report["spelled"],
                              skipped=report["skipped"], video=f"showcase/{stem}_{tier.slug}.mp4")
            except GenerationError:
                result["skipped"] = list(dict.fromkeys(glosses))
        results.append(result)
    context["results"] = results
    return render_template('showcase.html', **context)


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
