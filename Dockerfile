FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg libopus0 \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# requirements file is in repo root
COPY requirements /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# copy the whole repo into /app
COPY . /app/

ENV PYTHONUNBUFFERED=1

CMD ["python", "bot.py"]
