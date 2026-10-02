# One Dockerfile, three stages:
#   base    - Python plus the runtime libraries (shared by the other two)
#   test    - adds pytest/flake8 and runs the test suite when started
#   runtime - the small image that actually gets deployed

FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1     PIP_ROOT_USER_ACTION=ignore
WORKDIR /app
# Copy only the requirements first so this layer stays cached until the
# dependencies change, not every time the code changes.
COPY requirements.txt .
RUN pip install -r requirements.txt


FROM base AS test
COPY requirements-dev.txt .
RUN pip install -r requirements-dev.txt
COPY . .
# The pipeline runs this image as a container and copies the JUnit report out
# afterwards, even when tests fail.
CMD ["sh", "-c", "mkdir -p /reports && flake8 && pytest -v --junitxml=/reports/junit.xml --cov=sensor_dashboard --cov-report=term"]


FROM base AS runtime
ARG APP_VERSION=1.0.0
ARG GIT_COMMIT=unknown
ARG BUILD_NUMBER=local
ENV APP_VERSION=${APP_VERSION} \
    GIT_COMMIT=${GIT_COMMIT} \
    BUILD_NUMBER=${BUILD_NUMBER}
LABEL org.opencontainers.image.title="sensor-dashboard" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.revision="${GIT_COMMIT}"

RUN useradd --create-home --uid 10001 appuser
COPY sensor_dashboard ./sensor_dashboard
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"

# One worker with a few threads: the simulator and the metrics live in memory,
# so several worker processes would each have their own copy.
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "4", "sensor_dashboard.wsgi:app"]
