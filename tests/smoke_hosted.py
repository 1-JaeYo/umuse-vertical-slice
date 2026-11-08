#!/usr/bin/env python3
"""Exercise the real HTTP analysis flow using generated tones, never participant audio.

    python3 tests/smoke_hosted.py http://127.0.0.1:8766 --credentials-file /path/to/test.env

Produces a synthetic reading in the target service's test vault. This checks operation,
not the accuracy of music analysis. Keep the result separate from participant research.
"""
import argparse
import base64
import io
import json
from pathlib import Path
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import uuid
import wave

import numpy as np


def recording():
    rate = 44100
    t = np.arange(rate * 48) / rate
    audio = np.zeros_like(t)
    for start in range(0, 48, 4):
        roots = [(60, 64, 67), (57, 60, 64), (53, 57, 60), (55, 59, 62)]
        mask = (t >= start) & (t < start + 4)
        local = t[mask] - start
        for midi in roots[(start // 4) % 4]:
            audio[mask] += .13 * np.sin(2 * np.pi * 440 * 2 ** ((midi - 69) / 12) * local)
    # A deterministic beat pulse helps exercise beat-synchronous analysis.
    audio += .16 * np.sin(2 * np.pi * 90 * t) * np.exp(-45 * (t % .5))
    stream = io.BytesIO()
    with wave.open(stream, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes((np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())
    return stream.getvalue()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("--credentials-file", required=True)
    parser.add_argument("--read-code", help="Check a previously generated synthetic reading after restart")
    args = parser.parse_args()
    base = args.url.rstrip("/")
    values = dict(line.split("=", 1) for line in Path(args.credentials_file).read_text().splitlines() if "=" in line)
    auth = "Basic " + base64.b64encode(
        f"{values['UMUSE_USERNAME']}:{values['UMUSE_PASSWORD']}".encode()).decode()

    def get(path, authenticated=True):
        return urlopen(Request(base + path, headers={"Authorization": auth} if authenticated else {}), timeout=900)

    assert json.load(get("/healthz", False))["status"] == "ok"
    try:
        get("/", False)
        raise AssertionError("App was publicly readable")
    except HTTPError as error:
        assert error.code == 401
    html = get("/").read().decode()
    assert "uploaded to this private uMuse server" in html
    for path in ["/static/app.css", "/static/app.js", "/static/reading.css", "/static/reading.js",
                 "/static/sketch.js", "/static/notes.js", "/static/fonts/Ralmone-Regular.otf"]:
        assert get(path).status == 200, path
    if args.read_code:
        payload = json.load(get("/results/" + args.read_code))
        assert payload["identity"]["title"] == "Synthetic deployment test"
        print(f"Stored synthetic reading {args.read_code} survives restart; protected frontend/assets respond.")
        return
    boundary = "umuse-" + uuid.uuid4().hex
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="title"\r\n\r\n'
            f'Synthetic deployment test\r\n--{boundary}\r\n'
            'Content-Disposition: form-data; name="audio"; filename="synthetic.wav"\r\n'
            'Content-Type: audio/wav\r\n\r\n').encode() + recording() + f"\r\n--{boundary}--\r\n".encode()
    started = time.monotonic()
    request = Request(base + "/analyze", data=body, headers={"Authorization": auth, "Origin": base,
                      "Content-Type": "multipart/form-data; boundary=" + boundary})
    try:
        payload = json.load(urlopen(request, timeout=900))
    except HTTPError as error:
        print(error.read().decode())
        raise
    data = payload["data"]
    assert data["music"]["harmony"]["chord_source"]["tool"] == "Chordino"
    assert {m["source"] for m in data["comparisons"]["matches"]} == {"McGill Billboard", "Harmonix"}
    assert json.load(get("/results/" + payload["code"]))["data"] == data
    assert get("/reading/" + payload["code"]).status == 200
    print(json.dumps({"code": payload["code"], "synthetic_only": True,
        "elapsed_seconds": round(time.monotonic() - started, 1),
        "chord_source": "Chordino", "chord_changes": len(data["music"]["harmony"]["chord_changes"]),
        "comparison_sources": sorted({m["source"] for m in data["comparisons"]["matches"]}),
        "stored_reading": "verified", "frontend_assets": "verified"}))


if __name__ == "__main__":
    main()
