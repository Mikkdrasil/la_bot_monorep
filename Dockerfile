FROM python:3.10-slim

ENV PYTHONPATH=src
ENV PYTHONUNBUFFERED=1

RUN apt-get update && \
    apt-get install --assume-yes make g++ && \
    apt-get clean

RUN pip install uv

WORKDIR /opt/bot

COPY pyproject.toml uv.lock Makefile ./
COPY .env.example .env

RUN make venv

COPY src ./src
COPY tests ./tests
