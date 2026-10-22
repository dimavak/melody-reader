# Recognition server. Build from the repository root:
#   docker build -f server/Dockerfile -t melody-reader .
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt requirements.txt
COPY server/requirements.txt server-requirements.txt
RUN pip install --no-cache-dir -r requirements.txt -r server-requirements.txt
# homr downloads its models on first use; do it at build time so the first scan is not slow
RUN python -c "import homr.main as hm; hm.download_weights(False, False, False)"

COPY melody_reader melody_reader
COPY server/app.py .

RUN useradd -m -u 1000 app
USER app
ENV HOME=/home/app PYTHONUNBUFFERED=1
EXPOSE 7860
HEALTHCHECK --interval=60s --timeout=5s CMD curl -fs http://localhost:7860/ || exit 1
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]
