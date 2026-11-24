FROM node:24-bookworm-slim AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/index.html frontend/tsconfig.json frontend/vite.config.ts ./
COPY frontend/src ./src
RUN npm run build

FROM python:3.13-slim-bookworm
WORKDIR /app
ENV PYTHONPATH=/app/backend PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/doctor_compare ./backend/doctor_compare
COPY --from=frontend /build/dist ./frontend/dist
USER 10001:10001
CMD ["python", "-m", "uvicorn", "doctor_compare.main:app", "--host", "0.0.0.0", "--port", "8000"]
