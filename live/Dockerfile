# Gita Sarathi Live: the vertical 24/7 YouTube stream, the EscapeArenaLive way (no OBS, no browser).
FROM python:3.12-slim-bookworm

RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg libfribidi0 libraqm0 ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY gitalive ./gitalive
COPY run_live.py youtube_auth.py ./
# Bake the fonts into the image so the live stream never depends on outside sites
RUN python -m gitalive.fonts /app/fonts

ENV DATA_DIR=/app/data FONTS_DIR=/app/fonts PYTHONUNBUFFERED=1
CMD ["python", "run_live.py"]
