# WhatsAgent — FastAPI uygulama imajı
FROM python:3.12-slim

# Log'ların anlık akması ve .pyc üretilmemesi için
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Bağımlılıklar (mevcut requirements.txt olduğu gibi kullanılır)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Uygulama kaynağı
COPY . .

EXPOSE 8000

# Uygulama main.py içindeki "app" FastAPI nesnesi ile başlatılır
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
