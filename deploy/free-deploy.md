# Free Deployment Guide — Faceless System

Step-by-step instructions to deploy the entire faceless system on free-tier infrastructure.

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

## 2. Render (Free) — Background Worker

Deploy `orchestrator.py` as a background worker that runs continuously.

### Steps

1. Go to https://dashboard.render.com
2. **New +** → **Background Worker**
3. Connect your GitHub repo
4. Configure:

| Field | Value |
|-------|-------|
| **Name** | `faceless-engine` |
| **Region** | `Frankfurt (EU)` or `Oregon (US)` |
| **Branch** | `main` |
| **Root Directory** | *(leave blank)* |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `python orchestrator.py --mode full` |
| **Instance Type** | **Free** |

5. Add environment variables (optional):
   - `REDDIT_CLIENT_ID`
   - `REDDIT_CLIENT_SECRET`
   - `REDDIT_USER_AGENT`
   - `PORT` = `5000`
6. **Create Worker**

The worker will start the Flask server (internal), multiplier loop, and bootstrap cycle. Note: on the free tier, Render spins down after 15 minutes of inactivity — the background worker type stays alive as long as it produces log output, which the 60-second loop does.

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

## 4. Upstash Redis (Free) — Optional Queue

Use Upstash for cross-cycle state and queue management if you want to persist state outside the filesystem.

1. Go to https://console.upstash.com
2. **Create Database** → select **Free** tier (5k commands/day)
3. Copy the `UPSTASH_REDIS_REST_URL` and `UPSTASH_REDIS_REST_TOKEN`
4. Set as environment variables on Render

---

## 5. Free Tier Alternatives

| Service | Limits | Best For |
|---------|--------|----------|
| **PythonAnywhere** | 1 always-on task, 512 MB storage | Running the bootstrap on a schedule |
| **Railway** | $5 credit/month, 500 hours | Lightweight background workers |
| **Fly.io** | 3 shared VMs, 256 MB RAM each | Running the full engine with multiplier |
| **GitHub Actions** | 2000 min/month free | Running `--mode one-shot` on a cron schedule |
| **Koyeb** | 1 free app with always-on | Alternative to Render |

---

## Quick Deploy (One-Shot via Cron)

For a minimal setup that runs once daily on GitHub Actions:

```yaml
# .github/workflows/daily-bootstrap.yml
name: Daily Bootstrap
on:
  schedule:
    - cron: "0 6 * * *"   # 6 AM UTC daily
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

---

## Estimated Free Tier Capacity

| Resource | Monthly Free Limit | Faceless Usage |
|----------|-------------------|----------------|
| Render BG Worker | 750 hours | ~720 hours (always-on) |
| Cloudflare Pages | Unlimited bandwidth | Static HTML ~1 KB/visit |
| Upstash Redis | 5k commands/day | ~100 commands/cycle |
| GitHub Actions | 2000 min/month | ~2 min/run → 60 runs/month |
