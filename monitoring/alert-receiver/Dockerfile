FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY receiver.py test_receiver.py ./
RUN useradd --create-home --uid 10001 receiver
USER receiver
EXPOSE 5001
HEALTHCHECK --interval=15s --timeout=3s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5001/health', timeout=2)"
CMD ["python", "receiver.py"]
