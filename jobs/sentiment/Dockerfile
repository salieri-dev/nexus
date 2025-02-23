FROM python:3.9-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Create directories for logs and models
RUN mkdir -p /app/logs /app/models

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Run the analysis script
CMD ["python", "sentiment.py"]