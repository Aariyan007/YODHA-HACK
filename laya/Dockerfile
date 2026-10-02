# Laya decision service (CPU). Weights are NOT in the image: mount your fine-tuned folder at /models/laya.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 HF_HOME=/tmp/hf
WORKDIR /srv
# CPU-only torch keeps the image near 1.5 GB instead of 4 GB
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch && pip install "laya" fastapi "uvicorn[standard]"
COPY app.py .
RUN useradd --system --uid 10002 --no-create-home laya
USER laya
EXPOSE 8080
HEALTHCHECK --interval=20s --timeout=5s --start-period=120s --retries=5 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=4).status == 200 else 1)"
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
