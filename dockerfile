FROM ubuntu:22.04

# Install system packages
RUN apt-get update \
 && apt-get install -y wget ca-certificates python3 python3-pip \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

# Download the latest Telegram Bot API server binary
RUN wget -O /usr/local/bin/telegram-bot-api \
  https://github.com/tdlib/telegram-bot-api/releases/latest/download/telegram-bot-api \
 && chmod +x /usr/local/bin/telegram-bot-api

# Copy Python dependencies
COPY requirements.txt /app/requirements.txt
WORKDIR /app
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the code
COPY main.py .
COPY start.sh .
RUN chmod +x /app/start.sh

# Cloud Run uses $PORT; expose 8080 for the FastAPI app
ENV PORT=8080
CMD ["./start.sh"]
