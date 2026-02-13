# FAANG-level Movie Recommendation System

Quick scaffold combining FastAPI, a hybrid ML recommender, Redis caching, retraining pipeline and Prometheus metrics.

Steps (PowerShell on Windows):

1. Create virtualenv and install:
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

2. Copy env and edit:
```powershell
copy .env.example .env
# edit .env to set REDIS_URL, MODEL_PATH, RETRAIN_TOKEN
```

3. Run Redis (Docker recommended) and app:
```powershell
docker run -d --name redis -p 6379:6379 redis:7
uvicorn main:app --host 0.0.0.0 --port 8000
```

4. Endpoints:
- `GET /recommend/{user_id}?n=10` -> recommendations
- `POST /retrain` -> trigger retrain (use `RETRAIN_TOKEN` header `X-Retrain-Token`)
- `/metrics` -> Prometheus metrics

Scheduler & retraining
----------------------

Two ways to run periodic retraining safely:

- Local scheduler: run `scripts/scheduler.py`. It uses APScheduler and launches `scripts/retrain_runner.py`.
- Kubernetes CronJob: use `k8s/retrain-cronjob.yaml` which runs `scripts/retrain_runner.py` in a job.

 Both use a Redis-based lock so concurrent retrains are avoided. Configure lock TTL with `REDIS_RETRAIN_LOCK_TTL` in `.env`.

RedLock
------

This project can use RedLock for stronger distributed locking during retrain jobs.
Set `REDLOCK_ENABLED=true` and configure `REDLOCK_NODES` (comma-separated redis URLs) or leave `REDIS_URL` for a single node.

The retrain runner (`scripts/retrain_runner.py`) will prefer RedLock when enabled and fall back to a single-node Redis lock.

Local RedLock testing
---------------------

You can spin up three independent Redis instances locally and run the app using the included compose file:

```powershell
docker-compose -f docker-compose.redlock.yml up --build
```

This will create `redis1`, `redis2`, `redis3` and start the `app` with `REDLOCK_ENABLED=true` and `REDLOCK_NODES` configured to point to the three instances.

Metrics
-------

Lock acquisition/release metrics are exposed via the existing `/metrics` endpoint:

- `lock_acquire_total` — total lock acquire attempts
- `lock_acquire_failed_total` — failed lock acquire attempts
- `lock_release_total` — successful lock releases
- `lock_release_failed_total` — failed lock releases


Local scheduler example:
```powershell
# run scheduler as a background service
python scripts/scheduler.py
```

Kubernetes example:
```bash
kubectl apply -f k8s/retrain-cronjob.yaml
```

Complete run & build instructions
-------------------------------

1) Create virtualenv and install dependencies:
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

2) Run locally using `uvicorn`:
```powershell
docker run -d --name redis -p 6379:6379 redis:7
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

3) Run with docker-compose (single redis):
```powershell
docker-compose up --build
```

4) Run with redlock local test (3 redis nodes):
```powershell
docker-compose -f docker-compose.redlock.yml up --build
```

5) To run scheduled retrains locally (background process):
```powershell
python scripts/scheduler.py
```

6) To trigger retrain manually:
```powershell
curl -X POST http://localhost:8000/retrain -H "X-Retrain-Token: replace-this-secret-token"
```

Observability
-------------

- Metrics are exposed on `/metrics` for Prometheus. It includes lock and retrain metrics as well as basic request counters.
- Logs are written to stdout and can be collected by container logging drivers.

Frontend
--------

A simple React (Vite) frontend is available in the `frontend/` folder. It talks to the backend API on port `8000` by default.

Run frontend dev server:

```powershell
cd frontend
npm install
npm run dev
```

Build and serve with Docker Compose (serves on port `3000`):

```powershell
docker-compose up --build
# open http://localhost:3000
```

If you run Docker on Linux or from a remote host, set `VITE_API_BASE` in the `frontend` service environment to point to the backend API.


5. Docker compose: see `docker-compose.yml`.

Notes: This scaffold uses a simple hybrid approach (CF + content-based). Replace the sample CSV loader with your production data source and add authentication, monitoring, and CI as needed.