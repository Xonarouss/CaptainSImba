FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg libopus0 \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY CaptainSIMBA/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY CaptainSIMBA/ /app/

ENV PYTHONUNBUFFERED=1

CMD ["python", "bot.py"]
