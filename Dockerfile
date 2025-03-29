# Use official Python-Node.js image with specific versions
FROM nikolaik/python-nodejs:python3.10-nodejs19-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV PIP_NO_CACHE_DIR 1

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create and set working directory
WORKDIR /app

# Copy only requirements first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -U -r requirements.txt

# Copy the rest of the application
COPY . .

# Security hardening
RUN chmod 644 .env* || true && \
    find . -name "*.pyc" -delete && \
    find . -name "__pycache__" -exec rm -rf {} +

# Set non-root user
RUN useradd -m appuser && \
    chown -R appuser:appuser /app
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8080/health', timeout=2)" || exit 1

# Entry point
CMD ["bash", "start"]
