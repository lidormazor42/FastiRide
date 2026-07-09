FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    libzbar0 \
    tesseract-ocr \
    tesseract-ocr-heb \
    tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Run as a non-root user — if the app is ever compromised (e.g. via a
# malicious ticket-image upload), the attacker doesn't get root inside the
# container. Port 8000 is unprivileged, so nothing else needs to change.
RUN useradd --create-home --shell /usr/sbin/nologin appuser
USER appuser

ENV PORT=8000

EXPOSE 8000

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
