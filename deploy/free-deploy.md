# Free Deployment Guide — Faceless System

$0 forever infrastructure. No credit card required for any service.

---

## The Architecture

```
GitHub ──► GitHub Actions (Cron - content gen + posting)
                │
                ├──► Render Web Service (free, sleeps)
                │
                ▼
          Cloudflare Pages (landing page frontend)
                │
                ▼
          Supabase / Neon (leads, stats)
```

**Total: ₹0/month.**

---

## 1. GitHub Actions — The Engine (Cron Worker)

This runs content generation, demand fusion, and distribution on schedule. No server needed.

Create `.github/workflows/engine-cron.yml`:

```yaml
name: Faceless Engine Cron
on:
  schedule:
    - cron: "0 */4 * * *"
  workflow_dispatch:

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
```

**Cost: $0** — 2000 free min/month. One cycle ~2 min, 4/day = ~240 min.

---

## 2. Render — Landing Page Backend (Free Web Service)

Render's free web service sleeps after inactivity, but GitHub Actions wakes it on each cycle.

### Steps

1. Sign up at https://render.com (no credit card for free tier)
2. **New +** → **Web Service**
3. Connect GitHub repo
4. Configure:

| Field             | Value                             |
| ----------------- | --------------------------------- |
| **Name**          | `faceless-landing`                |
| **Branch**        | `main`                            |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `python offer/landing.py`         |
| **Instance Type** | **Free**                          |

5. **Deploy**

The free web service sleeps after 15 min of inactivity, but wakes on request (up to 30 sec cold start). The landing page will be available at `https://faceless-landing.onrender.com`.

### If Render asks for a card anyway

Skip the backend entirely. Use **Formspree** (free, no card) to capture leads from the static page:

---

## 2b. No-Backend Alternative — Fully Static

The landing page at `offer/landing/index.html` is pure static HTML. Deploy to Cloudflare Pages and use Formspree for the form:

1. Deploy `offer/landing/` to **Cloudflare Pages** (or Vercel, or Netlify — all free, no card)
2. Change form action in `index.html` from `/subscribe` to:
   ```
   https://formspree.io/f/YOUR_FORM_ID
   ```
3. Get a Formspree ID for free at https://formspree.io (no credit card)

Leads go to Formspree's dashboard. No server needed.

---

## 4. Database — Supabase (Free PostgreSQL)

Replace JSON file storage with a real DB. No credit card required.

### Steps

1. Go to https://supabase.com → **Start your project** (no card for free tier)
2. Copy connection string from Project Settings → Database
3. Set as `DATABASE_URL` GitHub Secret

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

**Free tier:** 500 MB DB, 5 GB bandwidth.

---

## 5. Frontend — Cloudflare Pages / Vercel (Free, No Card)

### Cloudflare Pages

1. https://dash.cloudflare.com → **Pages**
2. **Create a project** → **Connect to Git**
3. Build config:
   - **Build command:** `python offer/build_page.py`
   - **Build output:** `offer/landing`
4. **Deploy**

### Vercel (Alternative)

1. `npm i -g vercel`
2. `vercel --prod`
3. Point to `offer/landing/`

Both free, unlimited bandwidth, no credit card.

---

## Environment Variables

Set as GitHub Secrets for Actions + Render env vars:

```ini
REDDIT_CLIENT_ID=
REDDIT_CLIENT_SECRET=
REDDIT_USER_AGENT=faceless-engine/1.0

TWITTER_CONSUMER_KEY=
TWITTER_CONSUMER_SECRET=
TWITTER_ACCESS_TOKEN=
TWITTER_ACCESS_SECRET=

# Optional
DATABASE_URL=postgresql://...
PORT=5000
```

---

## Services That Require NO Credit Card

| Service | Purpose | Signup |
|---------|---------|--------|
| **GitHub Actions** | Cron engine | GitHub account |
| **Cloudflare Pages** | Static frontend | Cloudflare account |
| **Vercel** | Static frontend (alt) | GitHub login |
| **Netlify** | Static frontend (alt) | GitHub login |
| **Formspree** | Form backend | GitHub login |
| **Supabase** | PostgreSQL DB | GitHub login |
| **Neon** | Serverless Postgres (alt) | GitHub login |
| **Render** | Web service (may ask card) | Email (free tier exists) |

**Zero cards. Zero dollars. Zero bullshit.**

---

## Quick Deploy Checklist

- [ ] Push code to GitHub
- [ ] Create `.github/workflows/engine-cron.yml`
- [ ] Deploy `offer/landing/` to Cloudflare Pages
- [ ] Set up Formspree for email capture (or Render if no card issue)
- [ ] Set up Supabase DB (optional, replaces JSON files)
- [ ] Set GitHub Secrets for API keys
- [ ] Run first cycle manually via GitHub Actions UI

## Local Dev

```powershell
pip install -r requirements.txt
python orchestrator.py --mode one-shot
```