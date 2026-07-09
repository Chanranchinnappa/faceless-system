"""
Analytics & Multiplier Loop
Tracks what content converts and automatically amplifies winners.
"""

import json
import logging
import sys
import threading
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger("multiplier")
logger.setLevel(logging.INFO)
_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(
    logging.Formatter("%(asctime)s  %(levelname)-8s  %(message)s", datefmt="%H:%M:%S")
)
logger.handlers.clear()
logger.addHandler(_handler)

COMPOSITE_WEIGHTS = {"clicks": 3, "comments": 2, "shares": 2, "likes": 0.5}
WINNER_THRESHOLD = 20
AMPLIFY_TOP_N = 3
CONVERSION_RATE = 0.09
OFFER_PRICE = 47
DECAY_RATE = 0.05

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / "data"
STATE_FILE = DATA_DIR / "analytics.json"


def _default_state() -> dict:
    return {
        "posts": {},
        "engagement_history": {},
        "amplified_topics": [],
        "signal_log": [],
    }


def _composite(post: dict) -> float:
    return (
        post.get("clicks", 0) * COMPOSITE_WEIGHTS["clicks"]
        + post.get("comments", 0) * COMPOSITE_WEIGHTS["comments"]
        + post.get("shares", 0) * COMPOSITE_WEIGHTS["shares"]
        + post.get("likes", 0) * COMPOSITE_WEIGHTS["likes"]
    )


def _parse_hour_key(hour_key: str) -> datetime:
    try:
        dt = datetime.fromisoformat(hour_key)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return datetime.min.replace(tzinfo=timezone.utc)


def decay_score(
    posts: list[dict], reference_time: datetime | None = None
) -> list[dict]:
    """Reduce older posts' scores by 5% per hour since publication."""
    if reference_time is None:
        reference_time = datetime.now(timezone.utc)

    decayed = []
    for post in posts:
        base = _composite(post)
        ts = post.get("timestamp")
        hours = 0.0
        if ts:
            try:
                post_time = datetime.fromisoformat(ts)
                if post_time.tzinfo is None:
                    post_time = post_time.replace(tzinfo=timezone.utc)
                hours = max(0, (reference_time - post_time).total_seconds() / 3600)
            except (ValueError, TypeError):
                pass
        penalty = hours * DECAY_RATE
        entry = dict(post)
        entry["raw_score"] = base
        entry["decayed_score"] = max(0, base - penalty)
        entry["decay_hours"] = round(hours, 2)
        decayed.append(entry)
    return decayed


# ---------------------------------------------------------------------------
# PerformanceTracker
# ---------------------------------------------------------------------------


class PerformanceTracker:
    """Tracks and analyzes content performance across all platforms."""

    def __init__(self, state_file: str | Path | None = None):
        self.state_file = Path(state_file) if state_file else STATE_FILE
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self._state = _default_state()
        self._lock = threading.Lock()
        self.load_state()

    # -- persistence -------------------------------------------------------

    def save_state(self) -> None:
        with self._lock:
            try:
                with open(self.state_file, "w", encoding="utf-8") as f:
                    json.dump(self._state, f, indent=2, ensure_ascii=False, default=str)
                logger.debug("State saved to %s", self.state_file)
            except OSError as exc:
                logger.error("Failed to save state: %s", exc)

    def load_state(self) -> None:
        if self.state_file.exists():
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    self._state = json.load(f)
                logger.info(
                    "State loaded from %s (%d posts)",
                    self.state_file,
                    len(self._state.get("posts", {})),
                )
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning(
                    "Failed to load state: %s — using fresh state", exc
                )
                self._state = _default_state()
        else:
            self._state = _default_state()

    # -- tracking ----------------------------------------------------------

    def track_post(
        self,
        post_id: str,
        platform: str,
        topic: str,
        content_hash: str,
        timestamp: str | None = None,
    ) -> None:
        if timestamp is None:
            timestamp = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._state["posts"][post_id] = {
                "post_id": post_id,
                "platform": platform,
                "topic": topic,
                "content_hash": content_hash,
                "timestamp": timestamp,
                "likes": 0,
                "comments": 0,
                "shares": 0,
                "clicks": 0,
            }
            self._ensure_bucket(post_id)
        logger.info(
            "Tracked post %s on %s — topic: %s", post_id, platform, topic
        )
        self.save_state()

    def record_engagement(
        self,
        post_id: str,
        likes: int = 0,
        comments: int = 0,
        shares: int = 0,
        clicks: int = 0,
    ) -> None:
        with self._lock:
            if post_id not in self._state["posts"]:
                logger.warning("Post %s not found — cannot record engagement", post_id)
                return
            post = self._state["posts"][post_id]
            post["likes"] = post.get("likes", 0) + likes
            post["comments"] = post.get("comments", 0) + comments
            post["shares"] = post.get("shares", 0) + shares
            post["clicks"] = post.get("clicks", 0) + clicks
            self._record_bucket(post_id, likes, comments, shares, clicks)
        logger.debug(
            "Engagement recorded for %s: +%dL +%dC +%dS +%dCl",
            post_id, likes, comments, shares, clicks,
        )
        self.save_state()

    def _ensure_bucket(self, post_id: str) -> None:
        hour_key = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:00:00")
        if post_id not in self._state["engagement_history"]:
            self._state["engagement_history"][post_id] = {}
        if hour_key not in self._state["engagement_history"][post_id]:
            self._state["engagement_history"][post_id][hour_key] = {
                "likes": 0, "comments": 0, "shares": 0, "clicks": 0,
            }

    def _record_bucket(
        self, post_id: str, likes: int, comments: int, shares: int, clicks: int
    ) -> None:
        hour_key = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:00:00")
        self._ensure_bucket(post_id)
        bucket = self._state["engagement_history"][post_id][hour_key]
        bucket["likes"] += likes
        bucket["comments"] += comments
        bucket["shares"] += shares
        bucket["clicks"] += clicks

    # -- queries -----------------------------------------------------------

    def get_top_performers(
        self, min_engagement: float = 5, limit: int = 10
    ) -> list[dict]:
        with self._lock:
            posts = list(self._state["posts"].values())
        scored = decay_score(posts)
        filtered = [p for p in scored if p["raw_score"] >= min_engagement]
        filtered.sort(key=lambda p: p["decayed_score"], reverse=True)
        return filtered[:limit]

    def get_winners(self) -> list[dict]:
        with self._lock:
            posts = list(self._state["posts"].values())
        scored = decay_score(posts)
        return [p for p in scored if p["raw_score"] > WINNER_THRESHOLD]

    def get_post(self, post_id: str) -> dict | None:
        with self._lock:
            p = self._state["posts"].get(post_id)
            return dict(p) if p else None

    def all_posts(self) -> list[dict]:
        with self._lock:
            return [dict(p) for p in self._state["posts"].values()]

    # -- reporting ---------------------------------------------------------

    def attribution_report(self) -> str:
        with self._lock:
            posts = list(self._state["posts"].values())
            amplified = list(self._state.get("amplified_topics", []))

        if not posts:
            return "No data to report."

        topic_stats: dict[str, dict] = {}
        for p in posts:
            topic = p.get("topic", "unknown")
            if topic not in topic_stats:
                topic_stats[topic] = {
                    "count": 0, "likes": 0, "comments": 0, "shares": 0, "clicks": 0,
                }
            ts = topic_stats[topic]
            ts["count"] += 1
            ts["likes"] += p.get("likes", 0)
            ts["comments"] += p.get("comments", 0)
            ts["shares"] += p.get("shares", 0)
            ts["clicks"] += p.get("clicks", 0)

        top_topic = max(topic_stats, key=lambda t: topic_stats[t]["clicks"])
        top = topic_stats[top_topic]
        total_engagement = top["likes"] + top["comments"] + top["shares"] + top["clicks"]
        est_clicks = top["clicks"]
        est_conversions = int(est_clicks * CONVERSION_RATE)
        est_revenue = est_conversions * OFFER_PRICE
        amplified_count = len(amplified)
        amplified_str = f"True ({amplified_count}x)" if amplified_count else "False"

        return (
            "======= ATTRIBUTION REPORT =======\n"
            f'Top Topic: "{top_topic}"\n'
            f"Total Posts: {top['count']}\n"
            f"Total Engagement: {total_engagement}\n"
            f"Est. Clicks to Offer: {est_clicks}\n"
            f"Est. Conversions: {est_conversions}\n"
            f"Revenue Generated: ~${est_revenue}\n"
            f"Amplified: {amplified_str}\n"
            "================================"
        )


# ---------------------------------------------------------------------------
# MultiplierLoop
# ---------------------------------------------------------------------------


class MultiplierLoop:
    """Infinite loop that checks for winning content and amplifies it."""

    def __init__(
        self,
        tracker: PerformanceTracker | None = None,
        fusion_engine: Any | None = None,
        threshold: float = WINNER_THRESHOLD,
        interval_minutes: int = 30,
    ):
        self.tracker = tracker or PerformanceTracker()
        self.fusion_engine = fusion_engine
        self.threshold = threshold
        self.interval_seconds = interval_minutes * 60
        self._active = True
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    @property
    def active(self) -> bool:
        return self._active

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            logger.warning("MultiplierLoop already running")
            return
        self._active = True
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="MultiplierLoop"
        )
        self._thread.start()
        logger.info(
            "MultiplierLoop started (interval=%ds, threshold=%.1f)",
            self.interval_seconds, self.threshold,
        )

    def stop(self) -> None:
        with self._lock:
            self._active = False
        logger.info("MultiplierLoop stop signal sent")

    def _should_run(self) -> bool:
        with self._lock:
            return self._active

    # -- core logic --------------------------------------------------------

    def check_amplify(self) -> list[str]:
        winners = self.tracker.get_winners()
        if not winners:
            logger.info("No winners found (threshold=%.1f)", self.threshold)
            return []

        logger.info(
            "Found %d winner(s) above threshold %.1f", len(winners), self.threshold
        )

        # Sort by decayed score so fresh winners get priority
        winners.sort(key=lambda x: x.get("decayed_score", 0), reverse=True)

        amplified_files: list[str] = []
        seen_topics: set[str] = set()

        for w in winners:
            topic_title = w.get("topic", "")
            if not topic_title or topic_title in seen_topics:
                continue
            if len(amplified_files) >= AMPLIFY_TOP_N * 3:
                break

            seen_topics.add(topic_title)
            logger.info(
                "Amplifying topic: %s (raw=%.1f, decayed=%.1f)",
                topic_title, w.get("raw_score", 0), w.get("decayed_score", 0),
            )

            if self.fusion_engine and hasattr(self.fusion_engine, "amplify_winner"):
                topic_dict = {
                    "title": topic_title,
                    "subreddit": w.get("platform", "Entrepreneur"),
                    "source": "amplified",
                }
                try:
                    files = self.fusion_engine.amplify_winner(
                        topic_dict, additional_pieces=3
                    )
                    amplified_files.extend(files)
                except Exception as exc:
                    logger.error("Amplify failed for %s: %s", topic_title, exc)
            else:
                logger.warning(
                    "No fusion_engine — simulated amplify for %s", topic_title
                )

        if amplified_files:
            record = {
                "topic": list(seen_topics),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "files": amplified_files,
            }
            self.tracker._state.setdefault("amplified_topics", []).append(record)
            self.tracker.save_state()

        return amplified_files

    def _run_loop(self) -> None:
        logger.info("MultiplierLoop _run_loop entered")
        while self._should_run():
            try:
                logger.info("MultiplierLoop: checking for winners...")
                files = self.check_amplify()
                if files:
                    logger.info("Amplified %d new content pieces", len(files))
                else:
                    logger.info("No amplification needed this cycle")
            except Exception as exc:
                logger.error("MultiplierLoop cycle error: %s", exc)

            for _ in range(self.interval_seconds):
                if not self._should_run():
                    break
                time.sleep(1)

        logger.info("MultiplierLoop stopped")

    def run(self) -> None:
        self._run_loop()


# ---------------------------------------------------------------------------
# SignalDetector
# ---------------------------------------------------------------------------


class SignalDetector:
    """Watches for engagement spikes and recommends immediate amplification."""

    def __init__(
        self,
        tracker: PerformanceTracker | None = None,
        spike_threshold: float = 2.0,
        lookback_hours: int = 24,
    ):
        self.tracker = tracker or PerformanceTracker()
        self.spike_threshold = spike_threshold
        self.lookback_hours = lookback_hours

    def detect_spikes(self) -> list[dict]:
        """Return posts where latest hourly engagement > 200% of rolling average."""
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=self.lookback_hours)
        spikes: list[dict] = []

        with self.tracker._lock:
            posts = dict(self.tracker._state["posts"])
            history = dict(self.tracker._state["engagement_history"])

        for post_id, post in posts.items():
            post_history = history.get(post_id, {})
            if not post_history:
                continue

            hourly: list[tuple[str, int]] = []
            for hour_key, bucket in post_history.items():
                try:
                    hk = _parse_hour_key(hour_key)
                except (ValueError, TypeError):
                    continue
                total = (
                    bucket.get("likes", 0)
                    + bucket.get("comments", 0)
                    + bucket.get("shares", 0)
                    + bucket.get("clicks", 0)
                )
                hourly.append((hour_key, total))

            if not hourly:
                continue

            hourly.sort(key=lambda x: x[0])

            recent = [h for h in hourly if _parse_hour_key(h[0]) >= cutoff]
            if len(recent) < 2:
                continue

            avg = sum(h[1] for h in recent) / len(recent)
            if avg <= 0:
                continue

            latest_total = recent[-1][1]
            ratio = latest_total / avg

            if ratio >= self.spike_threshold:
                spike = {
                    "post_id": post_id,
                    "topic": post.get("topic", ""),
                    "platform": post.get("platform", ""),
                    "latest_engagement": latest_total,
                    "rolling_avg": round(avg, 2),
                    "ratio": round(ratio, 2),
                    "timestamp": now.isoformat(),
                    "recommendation": "Immediate amplification recommended",
                }
                spikes.append(spike)
                self.tracker._state.setdefault("signal_log", []).append(spike)
                self.tracker.save_state()
                logger.warning(
                    "SIGNAL: Spike on %s (%s) — ratio=%.2fx, topic=%s",
                    post_id, post.get("platform", "?"), ratio, post.get("topic", "?"),
                )

        return spikes


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def run_amplify_cycle(
    tracker: PerformanceTracker | None = None,
    fusion_engine: Any | None = None,
) -> dict[str, Any]:
    """One-shot: detect winners, amplify, detect spikes. Returns report."""
    tracker = tracker or PerformanceTracker()
    loop = MultiplierLoop(tracker=tracker, fusion_engine=fusion_engine)
    detector = SignalDetector(tracker=tracker)

    spikes = detector.detect_spikes()
    amplified = loop.check_amplify()

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "winners_found": len(tracker.get_winners()),
        "amplified_pieces": len(amplified),
        "amplified_files": amplified,
        "spikes_detected": len(spikes),
        "spike_events": spikes,
    }
