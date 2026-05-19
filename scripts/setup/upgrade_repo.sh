#!/bin/bash
set -e

echo " Upgrading Repo to Production-Grade (Adding Tests, Linting, Infra)..."

# 1. Add infra directory
mkdir -p infra
touch infra/.gitkeep

# 2. Add backend testing & linting structure
mkdir -p backend/tests
touch backend/tests/__init__.py

cat << 'EOF' > backend/pyproject.toml
[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I"] # flake8, pyflakes, isort
ignore = []

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
python_files = "test_*.py"
EOF

cat << 'EOF' > backend/tests/test_health.py
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
EOF

# Append dev dependencies to backend requirements
cat << 'EOF' >> backend/requirements.txt
# Dev Dependencies
pytest==8.0.0
pytest-asyncio==0.23.5
httpx==0.26.0
ruff==0.2.2
EOF

# 3. Add frontend testing & formatting
mkdir -p frontend/src/__tests__

cat << 'EOF' > frontend/src/__tests__/App.test.tsx
import { describe, it, expect } from 'vitest';

describe('App Test Suite', () => {
  it('should pass a basic truth check', () => {
    expect(true).toBe(true);
  });
});
EOF

cat << 'EOF' > frontend/.prettierrc
{
  "semi": true,
  "trailingComma": "all",
  "singleQuote": true,
  "printWidth": 100,
  "tabWidth": 2
}
EOF

# Note: Vite already sets up ESLint by default. We are just adding Vitest and Prettier scripts.
# We will use python to safely inject scripts into package.json without overwriting it
python3 -c '
import json

with open("frontend/package.json", "r") as f:
    data = json.load(f)

data["scripts"]["test"] = "vitest run"
data["scripts"]["test:watch"] = "vitest"
data["scripts"]["format"] = "prettier --write \"src/**/*.{ts,tsx,css,html}\""

with open("frontend/package.json", "w") as f:
    json.dump(data, f, indent=2)
'

# Move script to scripts folder
mv upgrade_repo.sh scripts/

echo " Production tools successfully added!"
echo " Now run the NPM install commands provided in the chat."
