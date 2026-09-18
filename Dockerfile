FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY rednexus ./rednexus
COPY config ./config
RUN useradd --uid 10001 --create-home nexus && mkdir -p /app/data && chown -R nexus:nexus /app/data
USER nexus
EXPOSE 8000
CMD ["python", "-m", "rednexus.platform.cli", "serve", "--host", "0.0.0.0"]
