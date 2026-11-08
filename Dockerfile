FROM python:3.14-slim-bookworm AS vamp-build
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential git libboost-dev libsndfile1-dev pkg-config \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /build
# Same revisions as the existing macOS detector. Build Linux binaries, not a new detector.
RUN git clone https://github.com/vamp-plugins/vamp-plugin-sdk.git vamp-plugin-sdk \
    && cd vamp-plugin-sdk \
    && git checkout 44c2487763eb248a933e9eff9169cfadee375009 \
    && ./configure \
    && make -j2 sdkstatic host
RUN git clone https://github.com/c4dm/nnls-chroma.git nnls-chroma \
    && cd nnls-chroma \
    && git checkout 4c5f214a75cb354f8d8c933e161377c5b4d83713 \
    && make -j2 -f Makefile.linux BOOST_ROOT=/usr/include
RUN mkdir -p /opt/vamp/plugins /opt/vamp/licenses \
    && cp vamp-plugin-sdk/host/vamp-simple-host /opt/vamp/ \
    && cp nnls-chroma/nnls-chroma.so /opt/vamp/plugins/ \
    && cp vamp-plugin-sdk/COPYING /opt/vamp/licenses/vamp-COPYING \
    && cp nnls-chroma/COPYING /opt/vamp/licenses/chordino-COPYING

FROM python:3.14-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    UMUSE_HOSTED=1 UMUSE_DATA_DIR=/data UMUSE_VAULT=/data/vault \
    UMUSE_VAMP_DIR=/opt/vamp OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
RUN apt-get update && apt-get install -y --no-install-recommends libsndfile1 libatomic1 libgomp1 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --from=vamp-build /opt/vamp /opt/vamp
COPY gunicorn.conf.py .
COPY scripts/ scripts/
COPY web/ web/
COPY corpus/ corpus/
RUN mkdir -p /data && chmod 700 /data \
    && python -c "import essentia.standard; import flask, numpy, scipy; from pathlib import Path; assert Path('/opt/vamp/plugins/nnls-chroma.so').is_file()"
EXPOSE 8765
CMD ["gunicorn", "--config", "gunicorn.conf.py", "web.app:app"]
