FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg libopus0 curl ca-certificates unzip \
 && rm -rf /var/lib/apt/lists/*

# Install Deno (JS runtime for yt-dlp EJS)
RUN curl -fsSL https://deno.land/install.sh | sh \
 && ln -s /root/.deno/bin/deno /usr/local/bin/deno

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

ENV PYTHONUNBUFFERED=1
CMD ["python", "main.py"]

