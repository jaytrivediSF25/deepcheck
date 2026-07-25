# deepcheck — transcription and claim verification in a container.
FROM python:3.12-slim

# git is needed to vendor the upstream transcriber at build time.
RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md ./
COPY deepcheck ./deepcheck
RUN pip install --no-cache-dir -e .

# Upstream calls the pre-1.2 classmethod API; deepcheck/compat.py bridges it,
# but pinning below 1.2 avoids relying on the shim inside the image.
RUN git clone --depth 1 \
      https://github.com/nickita-khylkouski/youtube-deepsummary.git \
      vendor/youtube-deepsummary \
 && pip install --no-cache-dir "youtube-transcript-api<1.2"

# Reports are written to the working directory; mount a volume over it.
VOLUME /work
WORKDIR /work

ENTRYPOINT ["deepcheck"]
CMD ["--help"]
