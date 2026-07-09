# Free Deployment Guide — Faceless System

Step-by-step instructions to deploy the entire faceless system on $0 infrastructure.

---

## 1. GitHub — Create Repo & Push Code

```bash
cd ~/Projects/faceless-system
git init
git add .
git commit -m "feat: initial faceless engine"
gh repo create faceless-system --public --push
```

Alternatively, create the repo manually on github.com, then:

```bash
git remote add origin https://github.com/Chanranchinnappa/faceless-system.git
git branch -M main
git push -u origin main
```

---

## 2. Always-On Server (Free)

Render's free tier **does not** include Background Workers. Use one of these instead:

### Option A: Fly.io (Recommended — 3 free VMs)

1. Install flyctl: `winget install FlyIO.flyctl` or `curl -fsSL https://fly.io/install.sh | sh`
2. Sign up: `fly auth login`
3. Deploy:
```bash
fly launch --name faceless-engine --region iad --now
fly deploy
```

Create a `fly.toml` in the project root:
```toml
app = "faceless-engine"

[env]
  PORT = "5000"

[http_service]
  internal_port = 5000
  force_https = true
  auto_stop_machines = false
  auto_start_machines = true
  min_machines_running = 1

[[services]]
  internal_port = 5000
  protocol = "tcp"

  [services.concurrency]
    hard_limit = 25
    soft_limit = 10

  [[services.ports]]
    port = 443
    handlers = ["tls"]

[[vm]]
  cpu_kind = "shared"
  cpus = 1
  memory_mb = 256
```

4. Start command: `python orchestrator.py --mode full`

### Option B: Koyeb (1 free app, always-on)

1. Sign up at https://app.koyeb.com
2. Create App → GitHub → select repo
3. Settings:
   - **Build command:** `pip install -r requirements.txt`
   - **Run command:** `python orchestrator.py --mode full`
   - **Port:** `5000`
4. Deploy — stays alive permanently on free tier.

### Option C: GitHub Actions Cron (No server, runs on schedule)

```yaml
# .github/workflows/daily-bootstrap.yml
name: Daily Bootstrap
on:
  schedule:
    - cron: "0 */6 * * *"   # every 6 hours
jobs:
  bootstrap:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -r requirements.txt
      - run: python orchestrator.py --mode one-shot
```

This runs the engine 4x/day for free (2000 min/month = plenty of headroom).

### Option D: PythonAnywhere (1 always-on task)

1. Sign up at https://www.pythonanywhere.com (free tier)
2. Upload code via Git clone or web upload
3. Go to **Tasks** tab → Create a scheduled task:
   - **Command:** `python /home/you/faceless-system/orchestrator.py --mode one-shot`
   - **Frequency:** `daily` or `every 6 hours`
4. For the Flask landing page, create a **Web app** pointing to `offer/landing.py`

---

## 3. Cloudflare Pages (Free) — Landing Page

Deploy the static landing page for lead capture.

### Prerequisites

Build the static HTML once:

```bash
python offer/build_page.py
```

This generates `offer/landing/index.html`.

### Steps

1. Go to https://dash.cloudflare.com → **Pages**
2. **Create a project** → **Connect to Git**
3. Select your repo
4. Configure:

| Field | Value |
|-------|-------|
| **Project name** | `faceless-landing` |
| **Production branch** | `main` |
| **Build command** | `python offer/build_page.py` |
| **Build output directory** | `offer/landing` |

5. **Save and Deploy**

### Form Handling

The landing page form points to `/subscribe`. Since Cloudflare Pages is a static host, use one of these free form backends:

- **Formspree** (free tier: 50 submissions/month) — change form action to `https://formspree.io/f/YOUR_FORM_ID`
- **Web3Forms** (free tier: 100 submissions/month)
- **Cloudflare Workers** (free tier: 100k requests/day) — create a worker at `/api/subscribe` that saves to KV

---

## 4. Free Tier Alternatives Table

| Service | Always-On? | Limits | Best For |
|---------|-----------|--------|----------|
| **Fly.io** | ✅ Yes | 3 shared VMs, 256 MB RAM, 3GB storage | Full engine + multiplier |
| **Koyeb** | ✅ Yes | 1 free app, 1GB RAM, 2GB storage | Full engine + multiplier |
| **PythonAnywhere** | ✅ Yes (1 web app) | 1 web app, 512MB storage | Landing page server |
| **GitHub Actions** | ❌ Scheduled only | 2000 min/month | One-shot bootstrap on cron |
| **Render** | ❌ Free web service sleeps | 750 hours, sleeps after 15min inactivity | Dev/testing only |
| **Railway** | ❌ $5 credit, 500 hours | Resets monthly | Short-term testing |
| **Oracle Cloud** | ✅ Yes | 2 free AMD VMs (always free) | Full VPS — most powerful |

---

## 5. Recommended Setup (True $0, No Sleeping)

```
┌──────────────────────────────────────────────┐
│  1. Fly.io (or Koyeb)                        │
│     → python orchestrator.py --mode full     │
│     → Engine runs 24/7, generates content,   │
│       tracks winners, amplifies              │
├──────────────────────────────────────────────┤
│  2. Cloudflare Pages                         │
│     → Static landing page (offer/landing/)   │
│     → Formspree for email capture            │
├──────────────────────────────────────────────┤
│  3. GitHub Actions (Optional booster)        │
│     → python orchestrator.py --mode one-shot │
│     → Every 6 hours as backup cycle          │
└──────────────────────────────────────────────┘
```

## 6. Environment Variables

Create a `.env` file (never committed):

```ini
# Required for posting (set these to deploy)
REDDIT_CLIENT_ID=
REDDIT_CLIENT_SECRET=
REDDIT_USER_AGENT=faceless-engine/1.0

TWITTER_CONSUMER_KEY=
TWITTER_CONSUMER_SECRET=
TWITTER_ACCESS_TOKEN=
TWITTER_ACCESS_SECRET=

# Optional
PORT=5000
```

---

## Quick Start (Local)

```powershell
pip install -r requirements.txt
python orchestrator.py --mode one-shot    # run once, see results
python orchestrator.py --mode full        # run forever
```