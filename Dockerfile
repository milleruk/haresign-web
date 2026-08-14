# syntax=docker/dockerfile:1
#
# haresign-web — public Haresign web layer.
#
# No database client libraries, no build toolchain: this application renders
# templates and serves static files, so the image stays small and its attack
# surface with it.

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencies first, so a template or CSS edit does not invalidate the layer
# that installs them.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Static files are hashed and compressed at build time rather than on boot, so
# every container in a rollout serves byte-identical assets and start-up does no
# work that could fail.
#
# SECRET_KEY is required when DEBUG is off (settings raises otherwise). The value
# here is used only by this build step, never at runtime — the real key comes
# from the environment — and collectstatic neither signs nor stores anything.
RUN SECRET_KEY=build-only-not-a-runtime-secret \
    DJANGO_SETTINGS_MODULE=config.settings \
    python manage.py collectstatic --noinput

# Run unprivileged. Nothing in the image needs to be written at runtime.
RUN useradd --system --create-home --uid 10001 haresign \
    && chown -R haresign:haresign /app
USER haresign

EXPOSE 8000

# The proxy health-checks /health/ too; this makes the container itself honest
# about its state so an unhealthy one is visible in `docker ps`.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health/', timeout=4).status == 200 else 1)"

# Two workers is right for a static marketing site; raise via the env var rather
# than editing this line.
CMD ["sh", "-c", "gunicorn config.wsgi:application \
     --bind 0.0.0.0:8000 \
     --workers ${GUNICORN_WORKERS:-2} \
     --threads ${GUNICORN_THREADS:-4} \
     --timeout ${GUNICORN_TIMEOUT:-30} \
     --access-logfile - \
     --error-logfile -"]
