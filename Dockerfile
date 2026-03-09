FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    playwright install chromium --with-deps && \
    playwright install-deps

COPY . .

CMD ["python", "app.py"]
