FROM python:3.11-slim

WORKDIR /app

COPY backend/requirements.txt ./requirements.txt

# Instalar PyTorch CPU-only primeiro (evita versão CUDA de 3GB)
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
        torch==2.2.0+cpu \
        --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir sentence-transformers==3.0.1 && \
    pip install --no-cache-dir -r requirements.txt

COPY backend/ .

RUN mkdir -p /app/data

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
