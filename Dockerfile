# Multi-stage production container for Autonomous AI Assistant
FROM python:3.11-slim-bookworm

# Set environment
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    NODE_ENV=production \
    PORT=8000

# Install Node.js 20, npm, curl, and essential system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    gnupg \
    procps \
    git \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" | tee /etc/apt/sources.list.d/nodesource.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Node.js requirements for WhatsApp Bridge
COPY bridges/whatsapp/package*.json bridges/whatsapp/
WORKDIR /app/bridges/whatsapp
RUN npm install --omit=dev

WORKDIR /app

# Copy application source code
COPY . .

# Ensure data directories exist
RUN mkdir -p data bridges/whatsapp/auth_info_baileys

# Make entrypoint executable
RUN chmod +x docker-entrypoint.sh run.sh start_tunnel.sh

EXPOSE 8000 3001

CMD ["./docker-entrypoint.sh"]
