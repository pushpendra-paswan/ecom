FROM python:3.12-slim

# Do not write .pyc files and print logs straight away
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# The app runs as a normal user (uid 1000), not as root. 1000 is also the usual first user on a Linux
# host, so files that the container writes into the mounted project folder belong to you.
RUN useradd --create-home --uid 1000 appuser

WORKDIR /app

# Install the Python packages first so Docker can cache this layer
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the project (docker compose also mounts it over /app for live reload)
COPY --chown=appuser:appuser . .

USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
