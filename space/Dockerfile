# Hugging Face Space (Docker). The deploy workflow puts this file at the Space root
# together with app.py, requirements.txt, server-requirements.txt and melody_reader/.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt server-requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r server-requirements.txt
# homr downloads its models on first use; do it now so a fresh Space answers sooner
RUN python -c "import homr.main as hm; hm.download_weights(False, False, False)"

COPY melody_reader melody_reader
COPY app.py .

RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user PYTHONUNBUFFERED=1
EXPOSE 7860
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]
