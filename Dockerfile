FROM python:3.9-alpine3.18
LABEL maintainer="ZongqiLyu"

ENV PYTHONUNBUFFERED 1

WORKDIR /eyeloveware_backend_api

COPY ./requirements.txt /tmp/requirements.txt
COPY . /eyeloveware_backend_api

EXPOSE 8000

RUN adduser --disabled-password --no-create-home elw-user && \
    python -m venv /py && \
    /py/bin/pip install --upgrade pip && \
    apk add --update --no-cache postgresql-client && \
    apk add --update --no-cache --virtual .tmp-build-deps \
    libffi-dev \
    build-base \
    postgresql-dev \
    musl-dev && \
    /py/bin/pip install -r /tmp/requirements.txt && \
    mkdir -p /eyeloveware_backend_api/staticfiles && \
    chown -R elw-user:elw-user /eyeloveware_backend_api && \
    su elw-user -s /bin/sh -c "/py/bin/python manage.py collectstatic --noinput" && \
    rm -rf /tmp && \
    apk del .tmp-build-deps

ENV PATH="/py/bin:$PATH"

USER elw-user

