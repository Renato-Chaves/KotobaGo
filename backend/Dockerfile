FROM python:3.15-slim

WORKDIR /app

# Install system dependencies for MeCab
RUN apt-get update && apt-get install -y \
    mecab \
    mecab-ipadic-utf8 \
    libmecab-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Source code is volume-mounted in dev, so no COPY needed here.
# In production you'd add: COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
