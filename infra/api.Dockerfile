FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY apps/api ./apps/api
RUN pip install --no-cache-dir .
ENV PYTHONPATH=/app/apps/api
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

