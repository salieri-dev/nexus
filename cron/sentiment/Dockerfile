FROM python:3.9-slim-buster

WORKDIR /app

# Install minimal dependencies in single layer
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Copy and install requirements in one layer
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    rm requirements.txt

# Copy script and required files
COPY sentiment.py .
COPY id2topic.json .
RUN mkdir -p logs models

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Simply run the script
CMD ["python", "sentiment.py"]