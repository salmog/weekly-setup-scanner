#!/bin/bash
set -e

echo " Bootstrapping Phase 1 Architecture in current directory..."

# 1. Create Directory Structure
mkdir -p backend/app/core
mkdir -p frontend/src/components
mkdir -p docker
mkdir -p scripts
mkdir -p docs

# 2. Write Root Files
cat << 'EOF' > .env.example
# System
PROJECT_NAME="HITL Trading System MVP"
VERSION="0.1.0"

# Postgres
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=hitl_trading
POSTGRES_HOST=postgres
POSTGRES_PORT=5432

# Redis
REDIS_HOST=redis
REDIS_PORT=6379

# Frontend
VITE_API_URL=http://localhost:8000
EOF

cat << 'EOF' > docker-compose.yml
version: '3.8'

services:
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-postgres}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-postgres}
      POSTGRES_DB: ${POSTGRES_DB:-hitl_trading}
    ports:
      - "5432:5432"
    volumes:
      - pg_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

  backend:
    build:
      context: ./backend
    ports:
      - "8000:8000"
    volumes:
      - ./backend/app:/code/app
    environment:
      - PYTHONPATH=/code
    env_file:
      - .env
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_started
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

  frontend:
    build:
      context: ./frontend
    ports:
      - "5173:5173"
    volumes:
      - ./frontend/src:/app/src
    env_file:
      - .env
    depends_on:
      - backend
    command: npm run dev

volumes:
  pg_data:
  redis_data:
EOF

# 3. Write Backend Files
cat << 'EOF' > backend/Dockerfile
FROM python:3.11-slim

WORKDIR /code

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
EOF

cat << 'EOF' > backend/requirements.txt
fastapi==0.109.2
uvicorn==0.27.1
pydantic==2.6.1
pydantic-settings==2.1.0
SQLAlchemy==2.0.25
asyncpg==0.29.0
redis==5.0.1
EOF

cat << 'EOF' > backend/app/core/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "HITL Trading System"
    VERSION: str = "0.1.0"

    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    POSTGRES_HOST: str
    POSTGRES_PORT: int

    REDIS_HOST: str
    REDIS_PORT: int

    @property
    def database_url(self) -> str:
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    class Config:
        env_file = ".env"

settings = Settings()
EOF

cat << 'EOF' > backend/app/main.py
from fastapi import FastAPI
from contextlib import asynccontextmanager
import logging
from app.core.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("System Bootstrapping...")
    logger.info(f"DB Connection string prepared: {settings.database_url}")
    logger.info(f"Redis target: {settings.REDIS_HOST}:{settings.REDIS_PORT}")
    yield
    logger.info("System Shutting down...")

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan
)

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "system": settings.PROJECT_NAME,
        "version": settings.VERSION
    }
EOF

touch backend/app/__init__.py
touch backend/app/core/__init__.py

# 4. Write Frontend Files
cat << 'EOF' > frontend/Dockerfile
FROM node:20-alpine

WORKDIR /app

COPY package.json .
RUN npm install
EOF

cat << 'EOF' > frontend/package.json
{
  "name": "hitl-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite --host 0.0.0.0 --port 5173",
    "build": "tsc && vite build"
  },
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0"
  },
  "devDependencies": {
    "@types/react": "^18.2.43",
    "@types/react-dom": "^18.2.17",
    "@vitejs/plugin-react": "^4.2.1",
    "typescript": "^5.2.2",
    "vite": "^5.0.8"
  }
}
EOF

cat << 'EOF' > frontend/vite.config.ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: true,
    watch: {
      usePolling: true
    }
  }
})
EOF

cat << 'EOF' > frontend/index.html
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>HITL Trading</title>
  </head>
  <body style="margin: 0; padding: 0; background-color: #121212; color: #ffffff; font-family: sans-serif;">
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
EOF

cat << 'EOF' > frontend/src/main.tsx
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.tsx'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
EOF

cat << 'EOF' > frontend/src/App.tsx
import React from 'react';
import Dashboard from './components/Dashboard';

function App() {
  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column' }}>
      <header style={{ padding: '1rem', borderBottom: '1px solid #333' }}>
        <h1 style={{ margin: 0, fontSize: '1.25rem' }}>HITL Breakout Trading System (MVP)</h1>
      </header>
      <main style={{ flex: 1, padding: '1rem' }}>
        <Dashboard />
      </main>
    </div>
  );
}

export default App;
EOF

cat << 'EOF' > frontend/src/components/Dashboard.tsx
import React, { useEffect, useState } from 'react';

const Dashboard = () => {
  const [healthStatus, setHealthStatus] = useState<string>('Checking backend...');

  useEffect(() => {
    fetch(`${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/health`)
      .then(res => res.json())
      .then(data => setHealthStatus(`Backend Status: ${data.status} (v${data.version})`))
      .catch(() => setHealthStatus('Backend Status: DISCONNECTED'));
  }, []);

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 300px', gap: '1rem', height: '100%' }}>
      <div style={{ backgroundColor: '#1e1e1e', border: '1px solid #333', borderRadius: '4px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <h2 style={{ color: '#666' }}>[ TradingView Lightweight Charts Placeholder ]</h2>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        <div style={{ backgroundColor: '#1e1e1e', padding: '1rem', border: '1px solid #333', borderRadius: '4px' }}>
          <h3 style={{ margin: '0 0 1rem 0', fontSize: '1rem' }}>System Health</h3>
          <p style={{ margin: 0, color: healthStatus.includes('healthy') ? '#4ade80' : '#f87171' }}>
            {healthStatus}
          </p>
        </div>
        <div style={{ backgroundColor: '#1e1e1e', padding: '1rem', border: '1px solid #333', borderRadius: '4px', flex: 1 }}>
          <h3 style={{ margin: '0 0 1rem 0', fontSize: '1rem' }}>Regime & Risk</h3>
          <p style={{ color: '#666' }}>[ Breadth Score Placeholder ]</p>
          <p style={{ color: '#666' }}>[ Risk Multiplier Placeholder ]</p>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
EOF

# 5. Setup .env and Git ignore
cp .env.example .env
echo -e "\nnode_modules/\n__pycache__/\n.env\n.DS_Store\nbootstrap_phase1.sh" >> .gitignore

echo " Phase 1 successfully scaffolded!"
