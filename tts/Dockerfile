FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir TTS flask

COPY server.py .

EXPOSE 5002

CMD ["python", "server.py"]