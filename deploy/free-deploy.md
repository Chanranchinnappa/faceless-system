# Free Deployment Guide — Faceless System

$0 forever infrastructure for the faceless engine.

---

## The Winning Architecture

```
GitHub ──► GitHub Actions (Cron - content gen + posting)
                │
                ▼
          Koyeb (Flask landing page backend)
                │
                ▼
          Supabase / Neon (leads, stats)
                │
                ▼
          Cloudflare R2 (assets if needed)
                │
                ▼
          Cloudflare Pages OR Vercel (frontend)
```

**Total: ₹0/month** until you get real traffic.

---

## 1. GitHub Actions — The Core Engine (Cron Worker)

This runs your content generation, demand fusion, and distribution on schedule.

Create `.github/workflows/engine-cron.yml`:

```yaml
name: Faceless Engine Cron
on:
  schedule:
    - cron: "0 */4 * * *"   # every 4 hours
  workflow_dispatch:          # manual trigger

jobs:
  engine-cycle:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install deps
        run: pip install -r requirements.txt
      - name: Run engine cycle
        run: python orchestrator.py --mode one-shot
      - name: Upload generated content
        uses: actions/upload-artifact@v4
        with:
          name: content-output
          path: content/
```

**Free tier:** 2000 min/month — one cycle takes ~2 min, so ~720 min/month for daily 4x runs. Well within limits.

---

## 2. Koyeb — Backend + Landing Page (Always-On)

Hosts the Flask landing page for lead capture.

### Steps

1. Sign up at https://app.koyeb.com
2. **Create App** → GitHub → select `faceless-system`
3. Configure:

| Field | Value |
|-------|-------|
| **Build command** | `pip install -r requirements.txt` |
| **Run command** | `python offer/landing.py` |
| **Port** | `5000` |
| **Environment variables** | `PORT=5000` |

4. **Deploy** — stays alive on free tier (may cold-start after idle, but doesn't sleep permanently).

---

## 3. Database — Supabase (Free PostgreSQL)

Replace the JSON file storage with a real DB that persists across deployments.

### Quick setup

1. Go to https://supabase.com → **New project**
2. Copy connection string from Project Settings → Database
3. Set as env var on Koyeb: `DATABASE_URL=postgresql://...`

### Schema

```sql
CREATE TABLE leads (
  id SERIAL PRIMARY KEY,
  email TEXT UNIQUE NOT NULL,
  subscribed_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE content_posts (
  id SERIAL PRIMARY KEY,
  topic TEXT,
  platform TEXT,
  posted_at TIMESTAMPTZ DEFAULT NOW(),
  engagement_score FLOAT DEFAULT 0,
  amplified BOOLEAN DEFAULT FALSE
);

CREATE TABLE stats (
  key TEXT PRIMARY KEY,
  value INTEGER DEFAULT 0
);
```

**Free tier:** 500 MB database, 5 GB bandwidth, unlimited API requests.

---

## 4. Frontend — Cloudflare Pages / Vercel (Free)

### Cloudflare Pages

1. Go to https://dash.cloudflare.com → **Pages**
2. **Create a project** → **Connect to Git**
3. Build config:
   - **Build command:** `python offer/build_page.py`
   - **Build output:** `offer/landing`
4. **Deploy**

### Vercel (Alternative)

1. `npm i -g vercel`
2. `vercel --prod`
3. Point to `offer/landing/` as output directory

Both are free with unlimited bandwidth for static sites.

---

## 5. File Storage — Cloudflare R2 (Free Tier)

If you need to store generated images, audio, or output files:

1. Go to https://dash.cloudflare.com → **R2**
2. Enable R2 (no credit card required)
3. Create bucket: `faceless-content`
4. Free tier: 10 GB storage + 10 million reads/month

---

## Environment Variables

Set these on Koyeb + GitHub Actions secrets:

```ini
# Required for posting
REDDIT_CLIENT_ID=
REDDIT_CLIENT_SECRET=
REDDIT_USER_AGENT=faceless-engine/1.0

TWITTER_CONSUMER_KEY=
TWITTER_CONSUMER_SECRET=
TWITTER_ACCESS_TOKEN=
TWITTER_ACCESS_SECRET=

# Database (optional, Supabase)
DATABASE_URL=postgresql://...

# App
PORT=5000
```

---

## Estimated Free Tier Capacity

| Service | Free Limit | Our Usage |
|---------|-----------|-----------|
| **GitHub Actions** | 2000 min/month | ~2 min/cycle, 4x/day = ~240 min |
| **Koyeb** | 1 app, always-on (may cold-start) | 1 Flask server |
| **Supabase** | 500 MB DB, 2 GB bandwidth | ~1 MB leads + stats |
| **Cloudflare Pages** | Unlimited bandwidth | Static HTML page |
| **Cloudflare R2** | 10 GB storage | Content files |

**Total: $0/month. Forever.**

---

## Quick Deploy Checklist

- [ ] Push code to GitHub
- [ ] Create `.github/workflows/engine-cron.yml`
- [ ] Deploy Flask to Koyeb
- [ ] Set up Supabase DB
- [ ] Deploy landing page to Cloudflare Pages
- [ ] Set environment variables on Koyeb + GitHub Secrets
- [ ] Run first cycle: `python orchestrator.py --mode one-shot`

## Local Dev

```powershell
pip install -r requirements.txt
python orchestrator.py --mode one-shot    # run once
python orchestrator.py --mode full        # run forever locally
```