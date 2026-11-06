FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TIKTOKEN_CACHE_DIR=/opt/tiktoken

WORKDIR /app

# Set INSTALL_EVAL=true to include the optional relevance-scoring model deps.
ARG INSTALL_EVAL=false
# Set INSTALL_DEV=true for the test image (pytest, hypothesis).
ARG INSTALL_DEV=false

COPY requirements.txt requirements-dev.txt requirements-eval.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && if [ "$INSTALL_DEV" = "true" ]; then pip install --no-cache-dir -r requirements-dev.txt; fi \
    && if [ "$INSTALL_EVAL" = "true" ]; then pip install --no-cache-dir -r requirements-eval.txt; fi

# Download the tokenizer files at build time so requests do not need internet
# access. If the download is blocked (e.g. a TLS-inspecting proxy), the build
# continues and pricing.py falls back to a byte-count upper bound.
RUN mkdir -p "$TIKTOKEN_CACHE_DIR" \
    && (python -c "import tiktoken; tiktoken.get_encoding('cl100k_base'); tiktoken.get_encoding('o200k_base')" \
        || echo "WARNING: tiktoken encodings not cached; token estimates will use the byte-count fallback")

COPY . .

RUN useradd --create-home --uid 10001 shieldwall
USER shieldwall

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
