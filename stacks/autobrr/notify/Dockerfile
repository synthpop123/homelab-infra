# Standalone notifier image so autobrr can run its stock image (no in-container Python).
# Built locally by the stack (Komodo deploys with `--build`); never pushed to a registry.
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

# Drop root.
RUN useradd --no-create-home --uid 10001 notify
USER 10001

EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
