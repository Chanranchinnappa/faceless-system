"""
Faceless Content Generator — Core AI Engine
Generates short-form video scripts + platform captions from trending topics.
Zero API keys, zero paid services, zero budget.
"""

import json
import logging
import re
import sys
import time
import html
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

logger = logging.getLogger("content_generator")
logger.setLevel(logging.INFO)
_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-8s  %(message)s", datefmt="%H:%M:%S"))
logger.handlers.clear()
logger.addHandler(_handler)

# ---------------------------------------------------------------------------
# Fallback topic seeds — used when all RSS sources fail
# ---------------------------------------------------------------------------
FALLBACK_TOPICS: list[dict[str, str]] = [
    {
        "title": "I built a $5k/month side project in public with zero marketing budget",
        "subreddit": "SideProject",
        "source": "fallback"
    },
    {
        "title": "The one metric that actually matters for early-stage startups",
        "subreddit": "Startups",
        "source": "fallback"
    },
    {
        "title": "How to get your first 100 customers without spending a dollar on ads",
        "subreddit": "Entrepreneur",
        "source": "fallback"
    },
    {
        "title": "Content repurposing strategy that saved me 20 hours a week",
        "subreddit": "DigitalMarketing",
        "source": "fallback"
    },
    {
        "title": "Why most side projects fail (and the 3 things successful ones do differently)",
        "subreddit": "SideProject",
        "source": "fallback"
    },
    {
        "title": "The reverse-engineered growth playbook I used to hit 10k users",
        "subreddit": "Startups",
        "source": "fallback"
    },
    {
        "title": "I tried 7 marketing channels so you don't have to — here's what worked",
        "subreddit": "DigitalMarketing",
        "source": "fallback"
    },
]

# ---------------------------------------------------------------------------
# Script templates — produce 3 variants per topic
# ---------------------------------------------------------------------------
SCRIPT_TEMPLATES: list[dict[str, str]] = [
    {
        "angle": "Curiosity Gap",
        "hook_tpl": 'Stop scrolling. {topic} — and it\'s not what you think.',
        "body_tpl": 'Most people get this backwards. They focus on {pain_point} when they should be focusing on {solution}. Here\'s the framework: step one — identify the real bottleneck. Step two — apply leverage where it compounds. Step three — repeat until it works.',
        "cta_tpl": 'I dropped the full breakdown in my bio.',
    },
    {
        "angle": "Hard Truth",
        "hook_tpl": 'Nobody wants to admit this but: {topic}.',
        "body_tpl": 'Here\'s the reality check. {pain_point} is killing your progress. But flip the script — when you {solution}, everything changes. I\'ve seen this pattern play out across dozens of founders and the ones who get it pull ahead fast.',
        "cta_tpl": 'Comment "DEEP" and I\'ll send you the system.',
    },
    {
        "angle": "Step-by-Step",
        "hook_tpl": 'Here\'s exactly how {topic} in 3 simple steps.',
        "body_tpl": 'Step 1: Stop doing {pain_point}. Step 2: Start {solution}. Step 3: Scale what works. That\'s it. No fluff, no gatekeeping. The people getting results right now are the ones taking action on basics while everyone chases shiny objects.',
        "cta_tpl": 'Follow for more no-BS breakdowns.',
    },
]

# ---------------------------------------------------------------------------
# Caption templates per platform
# ---------------------------------------------------------------------------
CAPTION_TEMPLATES: dict[str, str] = {
    "tiktok": "{hook} {body_summary} {cta} #faceless #sidehustle #{hashtag1} #{hashtag2} #{hashtag3}",
    "twitter": "{hook}\n\n{body_summary}\n\n{cta}\n\n#{hashtag1} #{hashtag2} #{hashtag3}",
    "reddit": "Here's a breakdown of {topic_lower}.\n\n{body_summary}\n\nWould love to hear what's worked for you.",
}

# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rsplit(" ", 1)[0] + "…"


def _extract_pain_point(title: str) -> str:
    title_lower = title.lower()
    if "fail" in title_lower or "mistake" in title_lower or "wrong" in title_lower:
        return "chasing the wrong strategy"
    if "budget" in title_lower or "money" in title_lower or "dollar" in title_lower:
        return "throwing money at the wrong channels"
    if "growth" in title_lower or "scale" in title_lower or "users" in title_lower:
        return "guessing instead of measuring"
    return "overcomplicating the process"


def _extract_solution(title: str) -> str:
    title_lower = title.lower()
    if "step" in title_lower or "framework" in title_lower:
        return "follow a repeatable system"
    if "customer" in title_lower or "user" in title_lower or "audience" in title_lower:
        return "talk to your customers daily"
    if "content" in title_lower or "market" in title_lower:
        return "create once, repurpose everywhere"
    if "side" in title_lower or "project" in title_lower:
        return "ship in public and iterate fast"
    return "focus on the highest-leverage activity"


def _pick_hashtags(topic: str, subreddit: str) -> list[str]:
    pool = [
        "entrepreneur", "sidehustle", "business", "startup", "marketing",
        "growth", "productivity", "hustle", "solopreneur", "make money online",
        "passive income", "small business", "digital marketing", "content creator",
        "faceless", "automation", "AI", "nobudget", "bootstrapped", "indiehacker",
    ]
    sub_map = {
        "Entrepreneur": ["entrepreneur", "solopreneur", "small business"],
        "SideProject": ["sidehustle", "indiehacker", "bootstrapped"],
        "Startups": ["startup", "growth", "bootstrapped"],
        "DigitalMarketing": ["digital marketing", "marketing", "content creator"],
    }
    chosen = sub_map.get(subreddit, pool[:3])
    chosen = chosen[:3]
    remaining = [t for t in pool if t not in chosen]
    import random
    random.shuffle(remaining)
    chosen.extend(remaining[:2])
    return chosen[:5]


# ---------------------------------------------------------------------------
# 1. Topic Scraper
# ---------------------------------------------------------------------------

def scrape_reddit_rss(subreddit: str, limit: int = 5) -> list[dict[str, str]]:
    """Grab hot posts from a subreddit via its public RSS feed."""
    url = f"https://www.reddit.com/r/{subreddit}/hot/.rss"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; FacelessEngine/1.0)"}
    items: list[dict[str, str]] = []

    try:
        import requests
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
    except Exception as exc:
        logger.warning("HTTP error for r/%s RSS: %s", subreddit, exc)
        return items

    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.content, "xml")
        entries = soup.find_all("entry")[:limit]

        for entry in entries:
            title_tag = entry.find("title")
            link_tag = entry.find("link")
            title = html.unescape(title_tag.text.strip()) if title_tag else ""
            link = ""
            if link_tag and link_tag.get("href"):
                link = link_tag["href"]
            if title:
                items.append({"title": title, "subreddit": subreddit, "url": link, "source": "reddit_rss"})
    except Exception as exc:
        logger.warning("BS4 parse error for r/%s: %s", subreddit, exc)

    return items


def scrape_topics() -> list[dict[str, str]]:
    """Scrape trending topics across target subreddits. Falls back to seeds on failure."""
    SUBREDDITS = ["Entrepreneur", "SideProject", "Startups", "DigitalMarketing"]
    all_topics: list[dict[str, str]] = []

    for sub in SUBREDDITS:
        try:
            posts = scrape_reddit_rss(sub)
            all_topics.extend(posts)
            logger.info("Scraped %d posts from r/%s", len(posts), sub)
        except Exception as exc:
            logger.error("Failed to scrape r/%s: %s", sub, exc)

    if not all_topics:
        logger.warning("All RSS sources failed — using fallback topic seeds")
        all_topics = FALLBACK_TOPICS.copy()

    # Deduplicate by title (case-insensitive)
    seen: set[str] = set()
    unique: list[dict[str, str]] = []
    for t in all_topics:
        key = t["title"].lower().strip()
        if key not in seen:
            seen.add(key)
            unique.append(t)

    return unique


# ---------------------------------------------------------------------------
# 2. Script Generator
# ---------------------------------------------------------------------------

def generate_scripts(topic: dict[str, str]) -> list[dict[str, str]]:
    """Generate 3 script variants for a given topic."""
    title = topic["title"]
    subreddit = topic.get("subreddit", "Entrepreneur")
    pain = _extract_pain_point(title)
    soln = _extract_solution(title)
    hashtags = _pick_hashtags(title, subreddit)

    variants: list[dict[str, str]] = []
    for tpl in SCRIPT_TEMPLATES:
        hook = tpl["hook_tpl"].format(topic=title)
        body = tpl["body_tpl"].format(topic=title, pain_point=pain, solution=soln)
        cta = tpl["cta_tpl"]
        scripts_hashtags = hashtags[:3]

        variants.append({
            "angle": tpl["angle"],
            "hook": hook,
            "body": body,
            "cta": cta,
            "full_script": f"{hook}\n\n{body}\n\n{cta}",
            "hashtags": scripts_hashtags,
        })

    return variants


# ---------------------------------------------------------------------------
# 3. Caption Generator
# ---------------------------------------------------------------------------

def generate_captions(topic: dict[str, str], variants: list[dict[str, str]]) -> dict[str, str]:
    """Generate one platform-optimized caption per platform."""
    title = topic["title"]
    hashtags = _pick_hashtags(title, topic.get("subreddit", "Entrepreneur"))
    first_variant = variants[0]

    body_summary = _truncate(first_variant["body"], 100)
    caption_data = {
        "hook": first_variant["hook"],
        "body_summary": body_summary,
        "cta": first_variant["cta"].rstrip("."),
        "topic_lower": title.lower(),
        "hashtag1": hashtags[0] if len(hashtags) > 0 else "faceless",
        "hashtag2": hashtags[1] if len(hashtags) > 1 else "sidehustle",
        "hashtag3": hashtags[2] if len(hashtags) > 2 else "growth",
    }

    captions: dict[str, str] = {}
    for platform, tpl in CAPTION_TEMPLATES.items():
        raw = tpl.format(**caption_data)
        captions[platform] = _truncate(raw, 180)

    return captions


# ---------------------------------------------------------------------------
# 4. Save Output
# ---------------------------------------------------------------------------

def save_content(topic: dict[str, str], scripts: list[dict[str, str]],
                 captions: dict[str, str]) -> Path:
    """Save generated content as a JSON file in ../content/."""
    output_dir = Path(__file__).resolve().parent.parent / "content"
    output_dir.mkdir(parents=True, exist_ok=True)

    slug = _slugify(topic["title"][:60])
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"{slug}_{timestamp}.json"
    filepath = output_dir / filename

    payload: dict[str, Any] = {
        "meta": {
            "generated_at": datetime.utcnow().isoformat(),
            "source": topic.get("source", "reddit_rss"),
            "subreddit": topic.get("subreddit", ""),
            "url": topic.get("url", ""),
        },
        "topic": topic["title"],
        "scripts": scripts,
        "captions": captions,
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    logger.info("Saved -> %s", filepath)
    return filepath


# ---------------------------------------------------------------------------
# 5. Main — headless generation for 5 trending topics
# ---------------------------------------------------------------------------

def retry(fn, *args, retries: int = 1, **kwargs):
    """Retry wrapper: attempts fn, waits 2 s, retries once on failure."""
    last_exc = None
    for attempt in range(retries + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            last_exc = exc
            logger.warning("Attempt %d/%d failed for %s: %s",
                           attempt + 1, retries + 1, fn.__name__, exc)
            if attempt < retries:
                time.sleep(2)
    raise last_exc  # type: ignore[misc]


def run_pipeline(topic: dict[str, str]) -> Path | None:
    """Run the full generation pipeline for a single topic."""
    try:
        scripts = retry(generate_scripts, topic)
        captions = retry(generate_captions, topic, scripts)
        filepath = retry(save_content, topic, scripts, captions)
        return filepath
    except Exception as exc:
        logger.error("Pipeline failed for topic [%s]: %s",
                     topic.get("title", "?"), exc)
        return None


def main() -> None:
    logger.info("=" * 56)
    logger.info("  Faceless Content Generator — Engine v1")
    logger.info("=" * 56)

    topics = retry(scrape_topics)
    logger.info("Found %d unique trending topics", len(topics))

    # Process up to 5 topics
    batch = topics[:5]
    results: list[Path] = []

    for i, topic in enumerate(batch, 1):
        logger.info("")
        logger.info("[%d/%d] Processing: %s", i, len(batch), topic["title"])
        result = run_pipeline(topic)
        if result:
            results.append(result)

    logger.info("")
    logger.info("=" * 56)
    logger.info("  Done — %d/%d content files generated", len(results), len(batch))
    logger.info("=" * 56)


if __name__ == "__main__":
    main()
