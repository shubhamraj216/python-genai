# Production Dockerfile for Python GenAI API
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories with proper permissions
RUN mkdir -p /app/assets/generated/videos \
    /app/assets/avatars \
    /app/assets/db \
    /app/logs \
    && chmod -R 755 /app/assets \
    && chmod -R 755 /app/logs

# Expose port
EXPOSE 8000

# Health check (using curl which is more reliable than requests)
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/healthz || exit 1

# Run the application with uvicorn (production-ready)
# Use exec form to ensure proper signal handling
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info"]

