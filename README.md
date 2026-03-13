# 🏏 Cric Insights AI

AI-powered cricket insights app — player stats, match analysis, fantasy picks, and free-form Q&A powered by **Google Gemini**.

| Layer | Stack |
|---|---|
| Backend API | FastAPI + Uvicorn (Python 3.12) |
| UI | Streamlit (port 8502) |
| Frontend | Vite + React + TypeScript + Tailwind |
| LLM | Google Gemini (`gemini-2.0-flash-lite`) |
| Data | Cricsheet (Parquet via Polars) |
| Container | Docker (multi-stage) + Supervisord |

---

## 🚀 Quick Start — Local Development

### Prerequisites
- Python 3.12
- Node.js 20+ (for React frontend)
- A [Gemini API key](https://aistudio.google.com/app/apikey) (free tier available)

### 1. Clone & configure

```powershell
git clone <your-repo-url>
cd "Personal Apps"

# Copy the example env file and fill in your key
Copy-Item backend\.env.example backend\.env
notepad backend\.env
```

**Minimum required in `backend/.env`:**
```env
GEMINI_API_KEY=your_key_here
LLM_PROVIDER=gemini
LLM_MODEL=gemini-2.0-flash-lite
APP_PASSWORD=           # optional — leave blank to disable login
```

### 2. Backend

```powershell
cd "c:\Users\1223505\Personal Apps"
python -m venv .venv312
.venv312\Scripts\Activate.ps1
pip install -r backend/requirements.txt
python -m uvicorn backend.src.main:app --reload --host 127.0.0.1 --port 8002
```

API health check: http://127.0.0.1:8002/api/health

### 3. Streamlit UI

```powershell
# In a second terminal (venv activated)
cd "c:\Users\1223505\Personal Apps"
.venv312\Scripts\Activate.ps1
python -m streamlit run backend/ui/app.py --server.port 8502
```

Open: http://localhost:8502

### 4. React Frontend (optional)

```powershell
cd frontend
npm install
npm run dev   # http://localhost:5173
```

> **VS Code shortcut:** `Tasks: Run Task → "Run Backend and Frontend"`

---

## 🐳 Docker — Local Container

### Build & run

```powershell
# From the repo root
docker compose up --build
```

| Service | URL |
|---|---|
| Streamlit UI | http://localhost:8502 |
| FastAPI | http://localhost:8001 |
| React (via FastAPI) | http://localhost:8001 |

### Env vars for Docker

Create a `.env` file in the **repo root** (Docker Compose reads it automatically):

```env
GEMINI_API_KEY=your_key_here
APP_PASSWORD=your_secret_password
LLM_PROVIDER=gemini
LLM_MODEL=gemini-2.0-flash-lite
```

> ⚠️ Never commit `.env`. It is in `.gitignore`.

---

## ☁️ Deployment

### Option A — Railway (easiest, ~5 min)

1. Push repo to a **private** GitHub repo
2. Go to [railway.app](https://railway.app) → **New Project → Deploy from GitHub**
3. Select your repo
4. Railway auto-detects `Dockerfile`
5. Go to **Variables** and add:
   ```
   GEMINI_API_KEY = <your key>
   APP_PASSWORD   = <your password>
   LLM_PROVIDER   = gemini
   LLM_MODEL      = gemini-2.0-flash-lite
   ```
6. Go to **Settings → Networking** and expose port **8502** (Streamlit) as the public URL
7. Optionally also expose port **8001** for direct API access
8. Click **Deploy** — Railway builds the Docker image and launches it

**Cost:** Free tier = 500 hours/month. Upgrade for always-on.

---

### Option B — Fly.io

#### Install flyctl

```powershell
# Windows (PowerShell)
iwr https://fly.io/install.ps1 -UseBasicParsing | iex
```

#### First-time setup

```powershell
fly auth login
fly launch --no-deploy   # creates app, reads fly.toml
```

#### Create persistent volume for Cricsheet data

```powershell
fly volumes create cricsheet_data --size 2 --region sin
```

#### Set secrets

```powershell
fly secrets set GEMINI_API_KEY="your_key_here"
fly secrets set APP_PASSWORD="your_secret_password"
fly secrets set LLM_PROVIDER="gemini"
fly secrets set LLM_MODEL="gemini-2.0-flash-lite"
```

#### Deploy

```powershell
fly deploy
```

#### Check status

```powershell
fly status
fly logs
```

Your app will be live at `https://cric-insights-ai.fly.dev`

**Cost:** Free allowance covers 3 shared-CPU VMs + 3 GB volumes/month.

---

## 🔐 Security

| Feature | Details |
|---|---|
| Password protection | Set `APP_PASSWORD` env var. Users must log in before using the Streamlit UI. Leave blank to disable. |
| API keys | Never committed — loaded from env vars / secrets |
| CORS | Permissive for local dev; tighten `allow_origins` in `main.py` for production |
| Rate limiting | Gemini SDK retries on 429; consider adding a reverse proxy (Nginx/Caddy) for production |

---

## 📁 Project Structure

```
├── backend/
│   ├── src/
│   │   ├── main.py              # FastAPI app entry point
│   │   ├── routers/             # API route handlers
│   │   ├── services/            # LLM client, stats, settings
│   │   ├── providers/           # Cricsheet data provider
│   │   └── tools/               # Tool wrappers for AI
│   ├── ui/
│   │   └── app.py               # Streamlit UI
│   └── requirements.txt
├── frontend/                    # React + Vite + Tailwind
│   └── src/
├── Dockerfile                   # Multi-stage build
├── docker-compose.yml
├── supervisord.conf             # Runs FastAPI + Streamlit
├── fly.toml                     # Fly.io config
└── .env.example                 # Template — copy to backend/.env
```

---

## 🛠️ Tools Available in Streamlit UI

| Tool | Description |
|---|---|
| 💬 Ask AI | Free-form cricket Q&A |
| 🏏 Batter Stats | Career batting analysis for any player |
| 🎳 Bowler Stats | Career bowling analysis for any player |
| 🏟️ Venue Stats | Pitch conditions and venue records |
| ⚔️ Head-to-Head | Team vs team historical analysis |
| 📅 Recent Matches | Last N matches for any team |
| 🎯 Full Match Insights | Pre-match AI report: XI prediction, fantasy picks, match prediction |

---

## 📜 License

MIT © 2026
