FROM python:3.11-slim

WORKDIR /app

RUN addgroup --system dhan && adduser --system --ingroup dhan dhan

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY dhan_risk_manager.py .

RUN mkdir -p /app/logs && chown -R dhan:dhan /app

USER dhan

ENV LOG_FILE=/app/logs/dhan_risk_manager.log \
    LOG_LEVEL=INFO \
    PYTHONUNBUFFERED=1

CMD ["python", "dhan_risk_manager.py"]
