FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    build-essential \
    pkg-config \
    default-libmysqlclient-dev \
    curl \
    # WeasyPrint の依存ライブラリ（PDF 生成）
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libffi-dev \
    fontconfig \
    # 日本語フォント（PDF に日本語を正しく描画するため）
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY src/ /app/

ENV PYTHONPATH=/app
ENV DJANGO_SETTINGS_MODULE=config.settings
