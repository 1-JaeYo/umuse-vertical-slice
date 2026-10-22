#!/usr/bin/env python3
"""uMuse local web app: upload a track, analyse it on this computer, show the reading.

    python3 web/app.py

Then open http://127.0.0.1:8765. It listens on this computer only.

One request does the whole job: the upload is copied into the private vault under a
participant code (scripts/intake.py), then scripts/pipeline.py runs the analysis,
structure and comparisons and the data check. Results that fail the check are
never shown. One track is analysed at a time.
"""
import sys
import tempfile
import threading
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import vault  # noqa: E402
from intake import file_in_vault  # noqa: E402
from pipeline import PipelineError, readable, run  # noqa: E402

STATIC = Path(__file__).resolve().parent / "static"
ALLOWED = {".mp3", ".wav", ".aif", ".aiff", ".flac", ".m4a"}
MAX_MB = 200
HOST, PORT = "127.0.0.1", 8765

app = Flask(__name__, static_folder=str(STATIC), static_url_path="/static")
app.config["MAX_CONTENT_LENGTH"] = MAX_MB * 1024 * 1024
busy = threading.Lock()


def problem(status, message, action, details=None):
    """An error the page shows as: what happened, what to do, and optional details."""
    return jsonify(error={"message": message, "action": action, "details": details or []}), status


@app.get("/")
def index():
    return send_from_directory(STATIC, "index.html")


@app.post("/analyze")
def analyze():
    upload = request.files.get("audio")
    if upload is None or not upload.filename:
        return problem(400, "No audio file was chosen.", "Choose an audio file, then click Analyze.")
    name = Path(upload.filename).name
    ext = Path(name).suffix.lower()
    if ext not in ALLOWED:
        return problem(415, f"“{name}” isn't a file type the analysis can read.",
                       "Choose an MP3, WAV, AIFF, FLAC or M4A file.")
    title = request.form.get("title", "").strip()[:200] or Path(name).stem
    artist = request.form.get("artist", "").strip()[:200]

    if not busy.acquire(blocking=False):
        return problem(409, "Another track is being analysed right now.", "Wait for it to finish, then try again.")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            temp = Path(tmp) / f"upload{ext}"
            upload.save(temp)
            if temp.stat().st_size == 0:
                return problem(400, f"“{name}” is empty.", "Choose the file again, or export it again from your DAW.")
            readable(temp)  # a file that won't decode never reaches the vault
            code, audio, existing = file_in_vault(temp, artist, title, original_filename=name)
        data, problems = run(audio, code)
        if problems:
            return problem(422, "The analysis finished, but its results failed the data check, so they aren't shown.",
                           "This is a problem with the analysis, not with your file. Note the details below.",
                           problems[:20])
        return jsonify(code=code, existing=existing, data=data, identity=vault.identity(code))
    except PipelineError as e:
        return problem(422, f"The analysis stopped at this step: {e.step}.",
                       "If the file plays normally, try exporting it again as WAV or MP3 and analysing that.",
                       [str(e.detail)])
    except Exception as e:  # anything unexpected: say so plainly and keep the app running
        app.logger.exception("analysis failed")
        return problem(500, "Something went wrong on this computer while analysing the track.",
                       "Try again. If it happens again, the details below and the terminal running the app say more.",
                       [f"{type(e).__name__}: {e}"])
    finally:
        busy.release()


@app.errorhandler(413)
def too_large(_e):
    return problem(413, f"The file is larger than {MAX_MB} MB.",
                   "Export a shorter or compressed version (for example MP3) and try again.")


if __name__ == "__main__":
    print(f"uMuse is running at http://{HOST}:{PORT}  (Ctrl+C to stop)")
    app.run(host=HOST, port=PORT, debug=False, threaded=True)
