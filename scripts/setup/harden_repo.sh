#!/bin/bash
set -e
echo "🔒 Hardening Repository to Financial-Grade Production Standard..."

mkdir -p .github/workflows backend/alembic/versions backend/app/api/v1 backend/app/data_sources backend/app/ingestion backend/app/validators
touch backend/app/data_sources/__init__.py backend/app/ingestion/__init__.py backend/app/validators/__init__.py

if [ -f backend/app/api/data.py ]; then
    mv backend/app/api/data.py backend/app/api/v1/
    touch backend/app/api/v1/__init__.py
fi

cat << 'INNER_EOF' > backend/requirements.txt
fastapi==0.109.2
uvicorn==0.27.1
pydantic==2.6.1
pydantic-settings==2.1.0
SQLAlchemy==2.0.25
asyncpg==0.29.0
redis==5.0.1
alembic==1.13.1
structlog==24.1.0
INNER_EOF

cat << 'INNER_EOF' > backend/requirements-dev.txt
-r requirements.txt
pytest==8.0.0
pytest-asyncio==0.23.5
httpx==0.26.0
ruff==0.2.2
mypy==1.8.0
pre-commit==3.6.2
INNER_EOF

cat << 'INNER_EOF' > .editorconfig
root = true
[*]
charset = utf-8
end_of_line = lf
insert_final_newline = true
indent_style = space
indent_size = 4
trim_trailing_whitespace = true
[*.{ts,tsx,js,jsx,json,css,html,yml,yaml}]
indent_size = 2
INNER_EOF

cat << 'INNER_EOF' > .pre-commit-config.yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.2.2
    hooks:
      - id: ruff
        args: [ --fix ]
      - id: ruff-format
INNER_EOF

cat << 'INNER_EOF' > backend/pyproject.toml
[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "UP"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
python_files = "test_*.py"

[tool.mypy]
python_version = "3.11"
strict = true
plugins = ["pydantic.mypy", "sqlalchemy.ext.mypy.plugin"]
exclude = ["alembic"]

[tool.pydantic-mypy]
init_forbid_extra = true
init_typed = true
warn_required_dynamic_aliases = true
INNER_EOF

cat << 'INNER_EOF' > .github/workflows/ci.yml
name: CI Pipeline
on: [push, pull_request]
jobs:
  backend-checks:
    runs-on: ubuntu-latest
    defaults: { run: { working-directory: ./backend } }
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11', cache: 'pip' }
      - run: pip install -r requirements-dev.txt
      - run: ruff check .
      - run: ruff format --check .
      - run: mypy app
  frontend-checks:
    runs-on: ubuntu-latest
    defaults: { run: { working-directory: ./frontend } }
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '20', cache: 'npm' }
      - run: npm ci
      - run: npm run format
      - run: npm run test -- --run
INNER_EOF

cat << 'INNER_EOF' > frontend/vite.config.ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, host: true, watch: { usePolling: true } },
  test: { globals: true, environment: 'jsdom', setupFiles: ['./src/setupTests.ts'] }
})
INNER_EOF

cat << 'INNER_EOF' > frontend/src/setupTests.ts
import '@testing-library/jest-dom';
INNER_EOF

cat << 'INNER_EOF' > backend/app/core/logger.py
import structlog
import logging
import sys

def setup_logging():
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.INFO)
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer()
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    return structlog.get_logger()

logger = setup_logging()
INNER_EOF

cat << 'INNER_EOF' > backend/app/main.py
from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.core.config import settings
from app.core.database import engine
from app.core.logger import logger
from app.api.v1 import data

@asynccontextmanager
async def lifespan(app: FastAPI):
    await logger.ainfo("system_bootstrapping", db_url=settings.database_url)
    yield
    await logger.ainfo("system_shutting_down")
    await engine.dispose()

app = FastAPI(title=settings.PROJECT_NAME, version=settings.VERSION, lifespan=lifespan)
app.include_router(data.router, prefix="/api/v1")

@app.get("/health")
async def health_check():
    return {"status": "healthy", "system": settings.PROJECT_NAME, "version": settings.VERSION}
INNER_EOF

if [ -f scripts/bootstrap_phase1.sh ]; then mv scripts/bootstrap_phase1.sh scripts/setup/; fi
if [ -f scripts/build_phase2.sh ]; then mv scripts/build_phase2.sh scripts/setup/; fi
if [ -f scripts/upgrade_repo.sh ]; then mv scripts/upgrade_repo.sh scripts/setup/; fi
echo "✅ Hardening complete!"
