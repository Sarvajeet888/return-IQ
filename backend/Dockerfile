FROM python:3.11-slim

WORKDIR /app

# Install system deps (libmagic1 required by python-magic for real
# content-based file type verification, see return_mgmt.py upload_document)
RUN apt-get update && apt-get install -y curl libmagic1 && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# Run as a non-root user - the app never needs root privileges, and
# running as root is unnecessary attack surface if the container is ever
# compromised (e.g. via a future dependency RCE).
RUN groupadd -r appuser && useradd -r -g appuser -d /app appuser \
    && chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 8000

# Start — run migrations first. docker-compose.yml already overrides this
# with the same command, but that override only applies when the app is
# run *through* docker-compose. Any platform that just builds and runs
# this Dockerfile directly (Render, Railway, a bare `docker run`, etc.)
# would otherwise hit "no such table" on first login/write, since nothing
# else creates the schema. Baking the migration into the image's own
# CMD makes the image safe to run standalone.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2"]
