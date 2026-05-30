FROM 192.168.55.148:5000/mirror/docker.io/library/python:3.12-alpine

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV MARKETFLOW_DB=/data/marketflow.db

WORKDIR /app
RUN pip install --no-cache-dir pg8000==1.31.2
COPY app/ /app/app/

EXPOSE 8080
CMD ["python", "-m", "app.server"]
