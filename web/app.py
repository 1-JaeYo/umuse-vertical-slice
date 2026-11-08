#!/usr/bin/env python3
"""uMuse web app: upload a track, run the pipeline, show the reading.

    python3 web/app.py

Local mode listens on http://127.0.0.1:8765. The Docker image runs hosted mode
behind Gunicorn with mandatory researcher sign-in and persistent storage.

One request does the whole job: the upload is copied into the private vault under a
participant code (scripts/intake.py), then scripts/pipeline.py runs the analysis,
structure and comparisons and the data check. Results that fail the check are
never shown. One track is analysed at a time.

For a user session, run the track beforehand (python3 scripts/pipeline.py p01) and open
http://127.0.0.1:8765/reading/p01: the reading is on screen at once, and the upload comes
after it, so the content is tested before the interface and nothing has to run live.
"""
import json
import hmac
import os
import sys
import tempfile
import threading
from pathlib import Path

from flask import Flask, jsonify, request, Response
from werkzeug.middleware.proxy_fix import ProxyFix

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import vault  # noqa: E402
from intake import file_in_vault  # noqa: E402
from check import check  # noqa: E402
from pipeline import PipelineError, readable, run  # noqa: E402
from storage import RESULTS  # noqa: E402

STATIC = Path(__file__).resolve().parent / "static"
ALLOWED = {".mp3", ".wav", ".aif", ".aiff", ".flac", ".m4a"}
MAX_MB = 200
HOST, PORT = "127.0.0.1", 8765
HOSTED = os.environ.get("UMUSE_HOSTED") == "1"
USERNAME = os.environ.get("UMUSE_USERNAME", "")
PASSWORD = os.environ.get("UMUSE_PASSWORD", "")
if HOSTED and (not USERNAME or len(PASSWORD) < 24):
    raise RuntimeError("Hosted uMuse requires UMUSE_USERNAME and UMUSE_PASSWORD (at least 24 characters).")
if bool(USERNAME) != bool(PASSWORD):
    raise RuntimeError("Set both UMUSE_USERNAME and UMUSE_PASSWORD, or neither for local-only use.")
if HOSTED and (not os.environ.get("UMUSE_DATA_DIR") or not os.environ.get("UMUSE_VAULT")):
    raise RuntimeError("Hosted uMuse requires explicit persistent UMUSE_DATA_DIR and UMUSE_VAULT paths.")

app = Flask(__name__, static_folder=str(STATIC), static_url_path="/static")
app.config["MAX_CONTENT_LENGTH"] = MAX_MB * 1024 * 1024
if HOSTED:
    # Railway terminates HTTPS at its proxy. Do not trust a forwarded host.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=0, x_proto=1, x_host=0)
busy = threading.Lock()


def problem(status, message, action, details=None):
    """An error the page shows as: what happened, what to do, and optional details."""
    return jsonify(error={"message": message, "action": action, "details": details or []}), status


@app.before_request
def protect_readings():
    if request.path == "/healthz" and request.method in {"GET", "HEAD"}:
        return None
    if USERNAME:
        auth = request.authorization
        if not (auth and auth.type == "basic"
                and hmac.compare_digest((auth.username or "").encode(), USERNAME.encode())
                and hmac.compare_digest((auth.password or "").encode(), PASSWORD.encode())):
            return Response("Sign in to this private uMuse research app.", 401,
                            {"WWW-Authenticate": 'Basic realm="uMuse", charset="UTF-8"'})
    if request.method == "POST":
        # Browser Basic credentials are ambient: reject cross-site form submissions.
        origin = request.headers.get("Origin")
        if (origin and origin != request.host_url.rstrip("/")) or request.headers.get("Sec-Fetch-Site") == "cross-site":
            return problem(403, "This upload came from a different website.", "Upload from the uMuse page directly.")


@app.after_request
def privacy_headers(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "font-src 'self'; img-src 'self' data:; connect-src 'self'; "
        "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
    if HOSTED:
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
    return response


@app.get("/healthz")
def health():
    return jsonify(status="ok")


def app_shell():
    html = (STATIC / "index.html").read_text()
    description = ("The file is uploaded to this private uMuse server for analysis. Only upload music "
                   "you have permission to process here. " if HOSTED else "The analysis runs on this computer: ")
    return Response(html.replace("<!-- __UMUSE_PROCESSING_LOCATION__ -->", description), mimetype="text/html")


@app.get("/")
@app.get("/static/index.html")
def index():
    return app_shell()


@app.get("/reading/<code>")
def reading_page(code):
    """The session page: a track analysed beforehand, shown at once, with the upload after it."""
    return app_shell()


@app.get("/results/<code>")
def stored_reading(code):
    """A stored analysis (results/<code>.json), checked again before it is shown."""
    if not vault.CODE.match(code):
        return problem(404, f"“{code}” isn't a participant code.", "Use a code such as p01.")
    path = RESULTS / f"{code}.json"
    if not path.exists():
        return problem(404, f"There is no analysis for {code} yet.",
                       f"Run it before the session: python3 scripts/pipeline.py {code}")
    data = json.loads(path.read_text())
    problems = check(data)
    if problems:
        return problem(422, f"The stored analysis for {code} fails the data check, so it isn't shown.",
                       f"Run it again before the session: python3 scripts/pipeline.py {code}", problems[:20])
    try:
        identity = vault.identity(code)
    except KeyError:
        return problem(404, f"{code} isn't in the private vault.", "Check the code, or add the track first.")
    return jsonify(code=code, existing=False, data=data, identity=identity)


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
                       [] if HOSTED else [str(e.detail)])
    except Exception as e:  # anything unexpected: say so plainly and keep the app running
        if HOSTED:
            app.logger.error("Analysis failed (%s); participant details omitted", type(e).__name__)
        else:
            app.logger.exception("analysis failed")
        return problem(500, "Something went wrong while analysing the track.",
                       "Try again. If it happens again, contact the researcher.",
                       [] if HOSTED else [f"{type(e).__name__}: {e}"])
    finally:
        busy.release()


@app.errorhandler(413)
def too_large(_e):
    return problem(413, f"The file is larger than {MAX_MB} MB.",
                   "Export a shorter or compressed version (for example MP3) and try again.")


if __name__ == "__main__":
    print(f"uMuse is running at http://{HOST}:{PORT}  (Ctrl+C to stop)")
    app.run(host=HOST, port=PORT, debug=False, threaded=True)
