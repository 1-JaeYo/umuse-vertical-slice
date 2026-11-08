#!/usr/bin/env python3
"""Upload only app code and public corpora to an already configured Railway service.

    python3 scripts/deploy.py --project <id> --service <id> --environment <id>

Requires the official Railway CLI, signed in. No vault, results, screenshots, research
notes, local binaries or credentials are copied, even if they are tracked in Git.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent.parent
FILES = ["Dockerfile", ".dockerignore", "requirements.txt", "gunicorn.conf.py"]


def bundle(destination):
    for name in FILES:
        shutil.copy2(ROOT / name, destination / name)
    for directory in ["scripts", "web"]:
        (destination / directory).mkdir()
        for source in (ROOT / directory).glob("*.py"):
            shutil.copy2(source, destination / directory / source.name)
    shutil.copytree(ROOT / "web/static", destination / "web/static")
    shutil.copytree(ROOT / "corpus", destination / "corpus",
                    ignore=shutil.ignore_patterns(".git", ".DS_Store", "__pycache__"))
    forbidden = {".mp3", ".wav", ".aif", ".aiff", ".m4a", ".flac"}
    for source in destination.rglob("*"):
        if source.is_symlink() or source.suffix.lower() in forbidden or source.name == "participants.json":
            raise RuntimeError(f"Refusing unsafe deployment file: {source.relative_to(destination)}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--railway", default="railway", help="Path to the official Railway CLI")
    parser.add_argument("--project", required=True)
    parser.add_argument("--service", required=True)
    parser.add_argument("--environment", required=True, help="Exact Railway environment ID")
    args = parser.parse_args()
    # New Railway services no longer read railway.json. Set just this service's settings
    # through the current API; credentials remain separate Railway variables.
    settings = json.loads((ROOT / "railway-service-settings.json").read_text())
    query = ("mutation($service: String!, $environment: String!, $settings: ServiceInstanceUpdateInput!) { "
             "serviceInstanceUpdate(serviceId: $service, environmentId: $environment, input: $settings) }")
    subprocess.run([args.railway, "api", query, "--variables", json.dumps({
        "service": args.service, "environment": args.environment, "settings": settings})], check=True, cwd=ROOT)
    with tempfile.TemporaryDirectory(prefix="umuse-deploy-") as tmp:
        bundle(Path(tmp))
        subprocess.run([args.railway, "up", tmp, "--path-as-root", "--project", args.project,
                        "--service", args.service, "--environment", args.environment,
                        "--detach", "--yes"], check=True, cwd=ROOT)


if __name__ == "__main__":
    main()
