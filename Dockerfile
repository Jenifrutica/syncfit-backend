# syntax=docker/dockerfile:1.7
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv

COPY pyproject.toml README.md ./
COPY app ./app

# The sibling syncfit-* repos are private: the GitHub token is mounted as a
# BuildKit secret, used only for this step, and never stored in an image layer.
RUN --mount=type=secret,id=github_token \
    git config --global url."https://x-access-token:$(cat /run/secrets/github_token)@github.com/".insteadOf "https://github.com/" \
    && pip install ".[reasoning]" psycopg[binary] \
    && git config --global --unset-all url."https://x-access-token:$(cat /run/secrets/github_token)@github.com/".insteadOf \
    && rm -f /root/.gitconfig

RUN useradd --system --create-home appuser
USER appuser

EXPOSE 8000

# --proxy-headers: behind the ALB, so rate limiting sees the real client IP.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips=*"]
