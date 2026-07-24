# 🚀 AI-TPM Local Development Run Guide

## Prerequisites

| Requirement | Version | Check |
| :--- | :--- | :--- |
| Python | 3.12+ | `python --version` |
| Node.js | 22+ | `node --version` |
| npm | 10+ | `npm --version` |
| PostgreSQL | 14+ | Must be running on port `5432` |

---

## 📁 Project Structure

```
d:\ai project mnger\
├── backend/          ← FastAPI Python backend
├── frontend/         ← Next.js 15 TypeScript frontend
├── venv/             ← Python virtual environment
└── .env              ← Environment configuration
```

---

## ⚙️ One-Time Setup (First Run Only)

### 1. Create Python Virtual Environment
```powershell
cd "d:\ai project mnger"
python -m venv venv
```

### 2. Install Backend Dependencies
```powershell
cd "d:\ai project mnger"
venv\Scripts\pip install -r backend\requirements.txt
```

### 3. Configure Environment Variables
Make sure `d:\ai project mnger\.env` contains:
```env
DATABASE_URL=postgresql://postgres:12345@localhost:5432/ai_tpm
ASYNC_DATABASE_URL=postgresql+asyncpg://postgres:12345@localhost:5432/ai_tpm
SECRET_KEY=your-secret-key-here
USE_PGVECTOR=False
USE_REDIS=False
```

### 4. Run Database Migrations
```powershell
cd "d:\ai project mnger\backend"
..\venv\Scripts\alembic.exe upgrade head
```

### 5. Install Frontend Dependencies
```powershell
cd "d:\ai project mnger\frontend"
npm install
```

---

## 🖥️ Running the Backend (FastAPI)

Open a **PowerShell terminal** and run:

```powershell
cd "d:\ai project mnger"
$env:PYTHONPATH="backend"
venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**Expected output:**
```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started reloader process
INFO:     Application startup complete.
```

> [!TIP]
> The `--reload` flag enables hot-reloading — any changes to backend Python files automatically restart the server.

---

## 🌐 Running the Frontend (Next.js 15)

Open a **second PowerShell terminal** and run:

```powershell
cd "d:\ai project mnger\frontend"
npm run dev
```

**Expected output:**
```
▲ Next.js 15.5.20
  - Local:    http://localhost:3000
  - Network:  http://0.0.0.0:3000

✓ Starting...
✓ Ready in ~13s
```

---

## 🔗 Browser URLs

| Service | URL | Description |
| :--- | :--- | :--- |
| **Frontend Dashboard** | [`http://localhost:3000`](http://localhost:3000) | Executive AI Dashboard UI |
| **Backend Health** | [`http://localhost:8000/health`](http://localhost:8000/health) | Backend liveness check |
| **Swagger API Docs** | [`http://localhost:8000/docs`](http://localhost:8000/docs) | Interactive REST API explorer |
| **ReDoc API Docs** | [`http://localhost:8000/redoc`](http://localhost:8000/redoc) | Formal API documentation |

---

## 🧪 Running All Tests

```powershell
cd "d:\ai project mnger"
$env:PYTHONPATH="backend"
venv\Scripts\python.exe backend\tests\run_all_tests.py
```

Expected: `Suites Passed: 15 / 15`

---

## ⚡ Quick Start (Both Servers Together)

Run these two commands in **separate terminals** simultaneously:

**Terminal 1 — Backend:**
```powershell
cd "d:\ai project mnger"; $env:PYTHONPATH="backend"; venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**Terminal 2 — Frontend:**
```powershell
cd "d:\ai project mnger\frontend"; npm run dev
```

---

## 🛑 Stopping the Servers

Press `Ctrl + C` in each terminal to stop the respective server.

---

## 🐛 Troubleshooting

| Problem | Cause | Fix |
| :--- | :--- | :--- |
| `Cannot find module 'autoprefixer'` | Missing dev dependency | `cd frontend && npm install --save-dev autoprefixer` |
| Port 3000 already in use | Old process still running | Next.js will auto-switch to `3001` |
| `asyncpg connection refused` | PostgreSQL not running | Start PostgreSQL service |
| `alembic: command not found` | Wrong path | Use `..\venv\Scripts\alembic.exe` from `backend/` |
| `ModuleNotFoundError` in tests | PYTHONPATH not set | Set `$env:PYTHONPATH="backend"` before running |
