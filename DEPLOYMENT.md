# Railway deployment

The frontend and Flask analysis backend run together, at one HTTPS address. Local use
(`python3 web/app.py`) still works and uses the existing local vault. No participant data
is migrated automatically. Existing recordings need consent covering hosted processing.

## Service configuration

1. Use the repository's `Dockerfile` (Linux amd64), `railway-service-settings.json` and `gunicorn.conf.py`.
2. Attach a persistent volume at `/data` **before uploading any recordings**.
3. Set `UMUSE_USERNAME` to the researcher sign-in name and `UMUSE_PASSWORD` to a randomly
   generated password of at least 24 characters. Store these only in Railway variables
   and a local, git-ignored credential file. Never put them in source, the image or URLs.
4. The image sets `UMUSE_HOSTED=1`, `UMUSE_DATA_DIR=/data`, `UMUSE_VAULT=/data/vault`,
   and `UMUSE_VAMP_DIR=/opt/vamp`. Railway supplies `PORT`.
5. Use **one replica**. Gunicorn uses **one worker with four threads**, preserving the
   process-local intake/analysis lock while health checks and readings remain responsive.
6. Generate a Railway HTTPS domain. Every route and asset requires HTTP Basic sign-in,
   except `/healthz`, which returns only `{"status":"ok"}`. Keep access credentials private.

No database, task queue, Vercel proxy or external analysis API is required. Basic sign-in
is shared researcher access: it does **not** provide separate artist accounts or isolate
readings between people holding the credentials. Use it for supervised research only.

## Safe source upload

Install and sign in to the official Railway CLI, create the project and service, attach
the volume and set the variables above. Then run:

```sh
python3 scripts/deploy.py --project <project-id> --service <service-id> --environment <environment-id>
```

The script applies `railway-service-settings.json` to that specific service and environment
through Railway's API, then creates a temporary allowlisted source bundle: Docker/config files, Python
scripts, frontend assets and public annotation corpora. It excludes the participant vault,
raw analysis, generated results, reference files, screenshots, notes and local credentials.
This matters even for a private GitHub repository. `.dockerignore` separately restricts
the Docker build context. Build-time network access downloads public tools and packages;
runtime analysis runs inside the service.

The image builds Linux Chordino and Vamp from the same pinned commits as the local app,
with Python 3.14 and the same Essentia version. Existing macOS `.dylib` files are not uploaded.
Upstream licence notices for the compiled tools are included under `/opt/vamp/licenses`.
Ralmone remains a personal-use font; commercial deployment needs a suitable licence or
a replacement. Do not treat the private repository as a font licence.

## Checks

```sh
python3 -m unittest discover -s tests -v
docker build --platform linux/amd64 -t umuse .
```

Test an isolated volume and synthetic audio before using participant recordings. Verify
sign-in, upload, actual Chordino/Essentia analysis, both corpora, validation, stored readings,
and persistence after restarting. A working container proves the app runs; it does not
establish chord or section accuracy.

The app keeps the 200 MB upload limit and processes one track at a time in one request.
The server timeout is 900 seconds; the hosting proxy may also impose limits. If real
recordings exceed the available resources or request lifetime, report the failure honestly;
do not invent progress or findings. Memory use depends on track duration and structure
analysis; measure representative full-length recordings before inviting unsupervised use.

## Participant data and costs

Recordings live under `/data/vault`, raw output under `/data/raw`, and validated readings
are served from `/data/results`. The volume survives container replacement; it is not a
backup strategy. Deletion and backup retention need to follow the consent arrangement.
Names and song titles appear only to authenticated viewers. Hosted exceptions omit internal
paths, access logging is disabled, and responses use `no-store` and no-index headers.

Railway compute and storage consume trial credit or paid usage. This deployment does not
upgrade the subscription or add payment details. Check Railway usage before sessions;
trial expiry or exhausted credit can stop the app.

## Current deployment and verification — 2026-11-07

App: https://umuse-production.up.railway.app

The shared research username is `researcher`. Its generated password is in the local,
git-ignored `.env.railway` file (owner read/write only) and Railway's service variables.
The password is not in this document or the deployed source. Do not share it publicly.

Redeploy after installing and signing in to the official Railway CLI:

```sh
python3 scripts/deploy.py \
  --project 36f50859-2d6f-46e9-a868-fd255baaba50 \
  --service bd1d3a6c-7d09-4e92-aba1-7be10a9a295f \
  --environment 6e4fe999-dc5f-4205-a496-d37fb2e0a114
```

Six hosting tests passed: protected routes/assets, public health response, hosted upload
notice, rejected cross-site uploads, file-type/size validation, duplicate handling, busy
response, stored-result validation, private error messages and fail-closed startup.
A generated 48-second recording completed the actual Chordino/Essentia pipeline and
both corpus comparisons through the local Docker HTTP service and the live HTTPS service.
The local test reading survived a container restart; the hosted test reading survived the final
container replacement on Railway. The hosted test reading is explicitly
titled "Synthetic deployment test" and is not participant evidence.

A full 190.746-second supplied recording was also processed **only in the local Docker
test container**, completing in about 10 seconds; container peak memory was approximately
402 MiB. This is one resource measurement, not a guaranteed limit or an accuracy score.
No existing participant recordings, raw analysis, results or screenshots were uploaded.
The original local vault and reference files remain untouched. No paid subscription was added.
