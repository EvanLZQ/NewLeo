FROM python:3.9-alpine3.18
LABEL maintainer="ZongqiLyu"

ENV PYTHONUNBUFFERED 1

WORKDIR /leoptique_backend_api

COPY ./requirements.txt /tmp/requirements.txt
COPY . /leoptique_backend_api

EXPOSE 8000

RUN python -m venv /py && \
    /py/bin/pip install --upgrade pip && \
    apk add --update --no-cache postgresql-client && \
    apk add --update --no-cache --virtual .tmp-build-deps \
    libffi-dev \
    build-base \
    postgresql-dev \
    musl-dev && \
    /py/bin/pip install -r /tmp/requirements.txt && \
    rm -rf /tmp && \
    apk del .tmp-build-deps && \
    adduser --disabled-password --no-create-home leo-user

ENV PATH="/py/bin:$PATH"

USER leo-user

