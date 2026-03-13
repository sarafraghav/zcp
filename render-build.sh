#!/usr/bin/env bash
set -o errexit

# Install dependencies
pip install uv
uv sync --all-packages

# Django build steps (run from zcp-backend/)
cd zcp-backend
uv run python manage.py collectstatic --noinput
uv run python manage.py migrate --noinput
