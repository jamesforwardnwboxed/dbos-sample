FROM python:3.11-slim AS builder

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY stepchange/requirements.txt .

RUN pip install --upgrade pip && pip install --prefix=/install -r requirements.txt

FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY --from=builder /install /usr/local
COPY stepchange/control_plane ./control_plane
COPY stepchange/requirements.txt ./

EXPOSE 8001

CMD ["python", "-m", "control_plane.main"]
