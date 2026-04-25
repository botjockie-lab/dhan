FROM python:3.11-slim

# Install timezone data and an init process for clean signal handling on VPS hosts.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata tini \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN addgroup --system dhan && adduser --system --ingroup dhan dhan

COPY requirements.txt .
RUN pip install --no-cache-dir --disable-pip-version-check -r requirements.txt

COPY --chown=dhan:dhan dhan_risk_manager.py .

RUN mkdir -p /app/logs && chown -R dhan:dhan /app

USER dhan

ENV LOG_FILE=/app/logs/dhan_risk_manager.log \
    LOG_LEVEL=INFO \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Kolkata

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "dhan_risk_manager.py"]
