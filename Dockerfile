FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    wkhtmltopdf \
    libmagic1 \
    libmagickwand-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/

CMD ["python", "-m", "src.main"]