"""
Demand Fusion Engine — Trend Detection, Demand Scoring & Offer Injection
The brain. Detects what's trending in real-time, scores by demand, and
injects our offers into the right conversations at the right velocity.
"""

import json
import logging
import os
import sys
import time
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger("demand_fusion")
logger.setLevel(logging.INFO)
_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-8s  %(message)s", datefmt="%H:%M:%S"))
logger.handlers.clear()
logger.addHandler(_handler)

_HAVE_PRAW = False
try:
    import praw
    _HAVE_PRAW = True
except ImportError:
    pass

RELEVANCE_KEYWORDS = ["faceless", "automation", "income", "content", "side hustle"]

TARGET_SUBREDDITS = ["Entrepreneur", "SideProject", "Startups", "DigitalMarketing"]

TWITTER_SEARCH_KEYWORDS = [
    "make money online", "side hustle", "passive income",
    "AI automation", "content creator", "digital products",
]

FALLBACK_TRENDS: list[dict[str, Any]] = [
    {"title": "make money online", "source": "fallback", "score": 0, "comments": 0},
    {"title": "side hustle ideas", "source": "fallback", "score": 0, "comments": 0},
    {"title": "AI automation", "source": "fallback", "score": 0, "comments": 0},
    {"title": "passive income 2026", "source": "fallback", "score": 0, "comments": 0},
    {"title": "content creation tips", "source": "fallback", "score": 0, "comments": 0},
    {"title": "digital products", "source": "fallback", "score": 0, "comments": 0},
    {"title": "freelance income", "source": "fallback", "score": 0, "comments": 0},
    {"title": "solo business", "source": "fallback", "score": 0, "comments": 0},
    {"title": "no-code tools", "source": "fallback", "score": 0, "comments": 0},
    {"title": "sell digital downloads", "source": "fallback", "score": 0, "comments": 0},
]


# ---------------------------------------------------------------------------
# Trend Detector
# ---------------------------------------------------------------------------

class TrendDetector:
    """Scans Reddit (via PRAW) and Twitter (via public scrape) for trending topics."""

    def __init__(self, subreddits: list[str] | None = None, twitter_keywords: list[str] | None = None):
        self.subreddits = subreddits or TARGET_SUBREDDITS
        self.twitter_keywords = twitter_keywords or TWITTER_SEARCH_KEYWORDS
        self._reddit: praw.Reddit | None = None
        self._init_reddit()

    def _init_reddit(self) -> None:
        if not _HAVE_PRAW:
            logger.info("praw not installed — Reddit trends will return empty")
            return
        try:
            self._reddit = praw.Reddit(
                client_id=os.environ.get("REDDIT_CLIENT_ID", ""),
                client_secret=os.environ.get("REDDIT_CLIENT_SECRET", ""),
                user_agent=os.environ.get("REDDIT_USER_AGENT", "faceless-fusion/1.0"),
            )
            logger.info("TrendDetector: Reddit read-only client initialized")
        except Exception as exc:
            logger.warning("TrendDetector: Reddit init failed — %s", exc)

    def get_reddit_trends(self, limit: int = 10) -> list[dict[str, Any]]:
        """Scan target subreddits for hot posts. Returns topics with velocity."""
        if not self._reddit:
            logger.info("Reddit client not available — skipping Reddit trends")
            return []

        trends: list[dict[str, Any]] = []
        now = datetime.now(timezone.utc).timestamp()

        for sub_name in self.subreddits:
            try:
                sub = self._reddit.subreddit(sub_name)
                for post in sub.hot(limit=limit):
                    created = post.created_utc
                    hours_ago = max(0, (now - created) / 3600)

                    velocity = 0.0
                    if hours_ago > 0:
                        velocity = (post.score + post.num_comments) / hours_ago

                    trends.append({
                        "title": post.title,
                        "subreddit": sub_name,
                        "score": post.score,
                        "comments": post.num_comments,
                        "created_utc": created,
                        "hours_ago": round(hours_ago, 2),
                        "velocity": round(velocity, 2),
                        "url": post.url,
                        "source": "reddit",
                    })
            except Exception as exc:
                logger.warning("Failed to scan r/%s: %s", sub_name, exc)

        # Deduplicate by title
        seen: set[str] = set()
        unique: list[dict[str, Any]] = []
        for t in trends:
            key = t["title"].lower().strip()
            if key not in seen:
                seen.add(key)
                unique.append(t)

        logger.info("Reddit trends: %d unique topics across %d subreddits", len(unique), len(self.subreddits))
        return unique

    def get_twitter_trends(self) -> list[dict[str, Any]]:
        """Scrape public Twitter search results via nitter frontend. Falls back on failure."""
        trends: list[dict[str, Any]] = []
        now = datetime.now(timezone.utc).timestamp()

        for keyword in self.twitter_keywords:
            try:
                encoded = requests.utils.quote(keyword)
                url = f"https://nitter.net/search?q={encoded}&f=top"
                headers = {
                    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                                   "Chrome/120.0.0.0 Safari/537.36"),
                    "Accept": "text/html,application/xhtml+xml",
                }
                resp = requests.get(url, headers=headers, timeout=12)
                resp.raise_for_status()

                from bs4 import BeautifulSoup
                soup = BeautifulSoup(resp.text, "html.parser")
                tweet_cards = soup.select(".timeline-item") or soup.select("article") or []

                for card in tweet_cards[:5]:
                    title_el = card.select_one(".tweet-content") or card.select_one("p")
                    if not title_el:
                        continue
                    title = title_el.get_text(strip=True)
                    if not title or len(title) < 10:
                        continue

                    trends.append({
                        "title": title,
                        "subreddit": "twitter",
                        "score": 0,
                        "comments": 0,
                        "created_utc": now,
                        "hours_ago": 0,
                        "velocity": 0.0,
                        "url": "",
                        "source": "twitter",
                        "keyword": keyword,
                    })
            except Exception as exc:
                logger.debug("Twitter scrape failed for '%s': %s", keyword, exc)

        if not trends:
            logger.warning("Twitter scrape returned zero results — using fallback trends")
            return self.get_fallback_trends()

        seen: set[str] = set()
        unique: list[dict[str, Any]] = []
        for t in trends:
            key = t["title"].lower().strip()
            if key not in seen:
                seen.add(key)
                unique.append(t)

        logger.info("Twitter trends: %d unique topics scraped", len(unique))
        return unique

    def get_fallback_trends(self) -> list[dict[str, Any]]:
        """Return evergreen high-demand topics that always convert."""
        logger.info("Using fallback trends (%d evergreen topics)", len(FALLBACK_TRENDS))
        return [dict(t) for t in FALLBACK_TRENDS]


# ---------------------------------------------------------------------------
# Demand Scoring
# ---------------------------------------------------------------------------

def score_topic(topic_data: dict[str, Any]) -> float:
    """Score a topic 0-100 based on recency, engagement velocity, and relevance."""
    title = topic_data.get("title", "")
    hours_ago = topic_data.get("hours_ago", 999)
    velocity = topic_data.get("velocity", 0.0)

    # Recency score (weight 30%)
    if hours_ago <= 1:
        recency = 100
    elif hours_ago <= 2:
        recency = 80
    elif hours_ago <= 4:
        recency = 60
    elif hours_ago <= 8:
        recency = 40
    elif hours_ago <= 12:
        recency = 20
    else:
        recency = 10

    # Engagement velocity score (weight 40%)
    capped_velocity = min(velocity, 200)
    engagement = (capped_velocity / 200) * 100

    # Relevance score (weight 30%)
    title_lower = title.lower()
    matches = 0
    for kw in RELEVANCE_KEYWORDS:
        if kw in title_lower:
            matches += 1
    relevance = (matches / len(RELEVANCE_KEYWORDS)) * 100

    final_score = 0.3 * recency + 0.4 * engagement + 0.3 * relevance
    return round(min(final_score, 100), 1)


# ---------------------------------------------------------------------------
# Offer Injection
# ---------------------------------------------------------------------------

PROBLEM_WORDS = [
    "fail", "mistake", "wrong", "struggl", "hard", "difficult",
    "problem", "issue", "pain", "stress", "waste", "loss", "broken",
    "bad", "worst", "stop", "quit", "hate", "suck",
]

SOLUTION_WORDS = [
    "solution", "fix", "improve", "grow", "build", "create",
    "system", "framework", "step", "guide", "how to", "strategy",
    "proven", "simple", "easy", "win", "success", "scale",
    "automate", "optimize", "leverage", "compound",
]

CTA_TEMPLATES = {
    "soft": "I built a system for this, link in bio",
    "direct": "Full system is live at offersite.com/engine",
    "value_first": "Dropping the full breakdown in my free newsletter \u2014 link in bio",
}


def inject_offer(script: str) -> str:
    """Place the right CTA into a script based on sentiment analysis."""
    script_lower = script.lower()

    problem_count = sum(1 for w in PROBLEM_WORDS if w in script_lower)
    solution_count = sum(1 for w in SOLUTION_WORDS if w in script_lower)

    if problem_count > solution_count:
        cta = CTA_TEMPLATES["soft"]
        mode = "soft"
    elif solution_count > problem_count:
        cta = CTA_TEMPLATES["direct"]
        mode = "direct"
    else:
        cta = CTA_TEMPLATES["value_first"]
        mode = "value_first"

    injected = script + "\n\n" + cta
    logger.debug("Offer injected (%s mode): problem=%d solution=%d", mode, problem_count, solution_count)
    return injected


# ---------------------------------------------------------------------------
# Fusion Engine
# ---------------------------------------------------------------------------

class DemandFusionEngine:
    """Orchestrates trend detection, scoring, content gen, and distribution."""

    def __init__(
        self,
        interval_hours: int = 4,
        data_dir: str | Path | None = None,
    ):
        self.interval_hours = interval_hours
        self.cycles_per_day = 24 // interval_hours if interval_hours > 0 else 6

        base = Path(__file__).resolve().parent
        self.data_dir = Path(data_dir) if data_dir else (base / "data")
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.history_path = self.data_dir / "fusion_history.json"
        self.detector = TrendDetector()

        # Resolve content directory (shared with content_generator)
        self.content_dir = base.parent / "content"
        self.content_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            "DemandFusionEngine initialized — interval=%dh, cycles/day=%d",
            self.interval_hours, self.cycles_per_day,
        )

    # -----------------------------------------------------------------------
    # Cycle runner
    # -----------------------------------------------------------------------

    def run_cycle(self) -> dict[str, Any]:
        """Full fusion cycle: detect, score, generate, distribute, save history."""
        cycle_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        logger.info("")
        logger.info("=" * 56)
        logger.info("  Fusion Cycle [%s] — detecting trends", cycle_id)
        logger.info("=" * 56)

        # 1. Gather trends
        all_trends: list[dict[str, Any]] = []
        try:
            reddit_trends = self.detector.get_reddit_trends()
            all_trends.extend(reddit_trends)
            logger.info("  Reddit: %d topics", len(reddit_trends))
        except Exception as exc:
            logger.error("Reddit trend detection failed: %s", exc)

        try:
            twitter_trends = self.detector.get_twitter_trends()
            all_trends.extend(twitter_trends)
            logger.info("  Twitter: %d topics", len(twitter_trends))
        except Exception as exc:
            logger.error("Twitter trend detection failed: %s", exc)

        if not all_trends:
            logger.warning("No trends from any source — using fallbacks")
            all_trends = self.detector.get_fallback_trends()

        # 2. Score all trends
        scored: list[tuple[float, dict[str, Any]]] = []
        for t in all_trends:
            s = score_topic(t)
            scored.append((s, t))

        scored.sort(key=lambda x: x[0], reverse=True)

        logger.info("  Scored %d topics — top 3:", len(scored))
        for rank, (score, topic) in enumerate(scored[:5], 1):
            logger.info("    #%d  %5.1f  [%s]  %s", rank, score, topic.get("source", "?"), topic.get("title", "?")[:80])

        # 3. Pick top 3
        top3 = [t for _, t in scored[:3]]

        # 4. Generate content for each
        from engine.content_generator import run_pipeline

        generated_files: list[str] = []
        generation_results: list[dict[str, Any]] = []

        for i, topic in enumerate(top3, 1):
            logger.info("")
            logger.info("  [%d/3] Generating content for: %s", i, topic.get("title", "?")[:80])

            topic_dict = {
                "title": topic.get("title", ""),
                "subreddit": topic.get("subreddit", "Entrepreneur"),
                "url": topic.get("url", ""),
                "source": topic.get("source", "fusion"),
            }

            try:
                result_path = run_pipeline(topic_dict)
                if result_path:
                    generated_files.append(str(result_path))
                    generation_results.append({
                        "topic": topic_dict["title"],
                        "file": str(result_path),
                        "score": scored[i - 1][0] if i - 1 < len(scored) else 0,
                    })
                    logger.info("  -> Generated: %s", result_path.name)
                else:
                    logger.warning("  -> Pipeline returned None for topic")
            except Exception as exc:
                logger.error("  -> Pipeline failed: %s", exc)

        # 5. Distribute generated content
        distribution_results: dict[str, Any] = {}
        if generated_files:
            try:
                from distribution.distributor import run_distribution_cycle
                dist_result = run_distribution_cycle(str(self.content_dir))
                distribution_results = dist_result if isinstance(dist_result, dict) else {}
                logger.info("  Distribution: %d files processed", len(dist_result) if isinstance(dist_result, dict) else 0)
            except Exception as exc:
                logger.error("Distribution cycle failed: %s", exc)
        else:
            logger.warning("No content generated — skipping distribution")

        # 6. Build cycle report
        report: dict[str, Any] = {
            "cycle_id": cycle_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "interval_hours": self.interval_hours,
            "trends_scanned": len(all_trends),
            "topics_scored": len(scored),
            "generated_count": len(generated_files),
            "generated": generation_results,
            "distribution": distribution_results,
            "top_scores": [
                {"title": t.get("title", "?"), "score": s, "source": t.get("source", "?")}
                for s, t in scored[:3]
            ],
            "status": "complete",
        }

        # 7. Save cycle report
        self._append_history(report)
        self._save_last_cycle(report)

        logger.info("")
        logger.info("=" * 56)
        logger.info("  Cycle %s complete — %d content files generated",
                     cycle_id, len(generated_files))
        logger.info("=" * 56)

        return report

    # -----------------------------------------------------------------------
    # Amplify a winning topic
    # -----------------------------------------------------------------------

    def amplify_winner(self, topic: dict[str, Any], additional_pieces: int = 3) -> list[str]:
        """If a topic is getting engagement, generate more content on it."""
        logger.info("Amplifying topic: %s (%d additional pieces)", topic.get("title", "?"), additional_pieces)

        from engine.content_generator import run_pipeline
        generated: list[str] = []

        topic_dict = {
            "title": topic.get("title", ""),
            "subreddit": topic.get("subreddit", "Entrepreneur"),
            "url": topic.get("url", ""),
            "source": topic.get("source", "amplified"),
        }

        for i in range(additional_pieces):
            try:
                result_path = run_pipeline(topic_dict)
                if result_path:
                    generated.append(str(result_path))
                    logger.info("  Amplify piece %d/%d: %s", i + 1, additional_pieces, result_path.name)
                time.sleep(1)
            except Exception as exc:
                logger.error("  Amplify piece %d failed: %s", i + 1, exc)

        # Distribute amplified content
        if generated:
            try:
                from distribution.distributor import run_distribution_cycle
                run_distribution_cycle(str(self.content_dir))
            except Exception as exc:
                logger.error("Amplify distribution failed: %s", exc)

        logger.info("Amplify complete — %d additional pieces generated", len(generated))
        return generated

    # -----------------------------------------------------------------------
    # History persistence
    # -----------------------------------------------------------------------

    def _load_history(self) -> list[dict[str, Any]]:
        if self.history_path.exists():
            try:
                with open(self.history_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        return []

    def _append_history(self, entry: dict[str, Any]) -> None:
        history = self._load_history()
        history.append(entry)
        try:
            with open(self.history_path, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=2, ensure_ascii=False)
            logger.debug("History appended to %s (%d cycles total)", self.history_path, len(history))
        except OSError as exc:
            logger.error("Failed to write history: %s", exc)

    def _save_last_cycle(self, report: dict[str, Any]) -> None:
        last_path = self.data_dir / "last_cycle.json"
        try:
            with open(last_path, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            logger.debug("Last cycle report saved to %s", last_path)
        except OSError as exc:
            logger.error("Failed to save last cycle: %s", exc)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main() -> None:
    engine = DemandFusionEngine()
    report = engine.run_cycle()

    gen = report.get("generated", [])
    dist = report.get("distribution", {})

    print()
    print("=" * 56)
    print("  CYCLE SUMMARY")
    print("=" * 56)
    print(f"  Cycle ID:          {report.get('cycle_id', '?')}")
    print(f"  Trends scanned:    {report.get('trends_scanned', 0)}")
    print(f"  Topics scored:     {report.get('topics_scored', 0)}")
    print(f"  Content generated: {report.get('generated_count', 0)}")
    print(f"  Distribution:      {len(dist)} files")
    print()

    if gen:
        print("  Generated files:")
        for g in gen:
            print(f"    - {g.get('file', '?')}  (score: {g.get('score', 0)})")

    print()
    print(f"  Top scores:")
    for ts in report.get("top_scores", []):
        print(f"    {ts.get('score', 0):5.1f}  [{ts.get('source', '?')}]  {ts.get('title', '?')[:70]}")

    print()
    print(f"  Full report: {engine.data_dir / 'last_cycle.json'}")
    print("=" * 56)


if __name__ == "__main__":
    main()
