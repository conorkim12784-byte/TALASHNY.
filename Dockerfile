FROM python:3.10-slim

RUN apt-get update && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends \
       ffmpeg git curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY . /app/
WORKDIR /app/
RUN pip3 install --no-cache-dir --upgrade pip
RUN pip3 install --no-cache-dir -r requirements.txt

CMD ["python3", "-m", "YukkiMusic"]
