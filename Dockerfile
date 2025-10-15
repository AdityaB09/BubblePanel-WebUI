# === BubblePanel API with OCR (Tesseract + RapidOCR ONNX) ===
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# System deps for OpenCV headless and OCR stacks
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    libgl1 \
    libglib2.0-0 \
    libsm6 libxrender1 libxext6 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy monorepo parts
COPY backend/ backend/
COPY BubblePanel-main/ BubblePanel-main/
COPY backend/requirements.txt backend/requirements.txt

# Python deps (pins chosen for reliability)
RUN python -m pip install --upgrade pip && \
    pip install -r backend/requirements.txt && \
    # Optional: if BubblePanel-main has its own requirements.txt, uncomment next line:
    true

# Runtime env for backend process module
ENV BP_PYTHON=python \
    BP_SCRIPT=smoke_test.py \
    BP_REPO_ROOT=/app/BubblePanel-main \
    BP_UPLOAD_DIR=/app/uploads \
    PYTHONIOENCODING=utf-8

# Create uploads dir
RUN mkdir -p /app/uploads

EXPOSE 10000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "10000"]
