FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir . && pip install --no-cache-dir boto3

COPY . .
RUN mkdir -p data && chmod 777 data

ENV ENV=production

EXPOSE 8000

CMD ["python", "main.py"]
