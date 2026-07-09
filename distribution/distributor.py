"""
Silent distribution layer for faceless-system.
Reddit + Twitter/X distribution with auto-scraping and scheduling.
$0 budget — no paid APIs.
"""

import base64
import datetime
import hashlib
import hmac
import json
import logging
import os
import random
import time
import urllib.parse
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

_HAVE_PRAW = False
try:
    import praw  # noqa: F401

    _HAVE_PRAW = True
except ImportError:
    pass


# ── OAuth 1.0a Helpers ─────────────────────────────────────────────────


def _percent_encode(s):
    return urllib.parse.quote(str(s), safe="")


def _build_oauth_header(
    method, url, params, consumer_key, consumer_secret, access_token, access_token_secret
):
    oauth_params = {
        "oauth_consumer_key": consumer_key,
        "oauth_nonce": "".join(str(random.randint(0, 9)) for _ in range(32)),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_token": access_token,
        "oauth_version": "1.0",
    }
    all_params = {**params, **oauth_params}
    param_string = "&".join(
        f"{_percent_encode(k)}={_percent_encode(v)}"
        for k, v in sorted(all_params.items())
    )
    signature_base = "&".join(
        [method.upper(), _percent_encode(url), _percent_encode(param_string)]
    )
    signing_key = "&".join(
        [_percent_encode(consumer_secret), _percent_encode(access_token_secret or "")]
    )
    signature = base64.b64encode(
        hmac.new(
            signing_key.encode("utf-8"),
            signature_base.encode("utf-8"),
            hashlib.sha1,
        ).digest()
    ).decode("utf-8")
    oauth_params["oauth_signature"] = signature
    auth_header = "OAuth " + ", ".join(
        f'{_percent_encode(k)}="{_percent_encode(v)}"'
        for k, v in oauth_params.items()
    )
    return auth_header


# ── Reddit Distributor ─────────────────────────────────────────────────


class RedditDistributor:
    """Post and comment on Reddit via PRAW. Falls back to dry-run if creds missing."""

    def __init__(
        self,
        client_id=None,
        client_secret=None,
        user_agent=None,
        username=None,
        password=None,
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.user_agent = user_agent or "faceless-system/1.0"
        self.username = username
        self.password = password
        self._reddit = None
        self._dry_run = not all([client_id, client_secret, username, password])
        if not self._dry_run and _HAVE_PRAW:
            try:
                import praw

                self._reddit = praw.Reddit(
                    client_id=client_id,
                    client_secret=client_secret,
                    user_agent=self.user_agent,
                    username=username,
                    password=password,
                )
                logger.info("RedditDistributor authenticated as %s", username)
            except Exception as exc:
                logger.warning("Reddit auth failed, dry-run fallback: %s", exc)
                self._dry_run = True
        elif not _HAVE_PRAW:
            logger.warning("praw not installed — RedditDistributor in dry-run mode")

    def post_to_subreddit(self, subreddit, title, body):
        if self._dry_run:
            logger.info('[DRY-RUN] Would post to r/%s: "%s"', subreddit, title)
            return {"status": "dry-run", "subreddit": subreddit, "title": title}
        try:
            submission = self._reddit.subreddit(subreddit).submit(title, selftext=body)
            logger.info("Posted to r/%s: %s — %s", subreddit, title, submission.url)
            return {"status": "success", "id": submission.id, "url": submission.url}
        except Exception as exc:
            logger.error("Failed to post to r/%s: %s", subreddit, exc)
            return {"status": "error", "error": str(exc)}

    def comment_on_post(self, post_id, comment_body):
        if self._dry_run:
            logger.info(
                '[DRY-RUN] Would comment on %s: "%s..."', post_id, comment_body[:60]
            )
            return {"status": "dry-run", "post_id": post_id}
        try:
            submission = self._reddit.submission(id=post_id)
            comment = submission.reply(comment_body)
            logger.info("Commented on %s — comment %s", post_id, comment.id)
            return {"status": "success", "id": comment.id}
        except Exception as exc:
            logger.error("Failed to comment on %s: %s", post_id, exc)
            return {"status": "error", "error": str(exc)}


# ── Twitter / X Distributor ────────────────────────────────────────────


class TwitterDistributor:
    """Post tweets via API v2 with OAuth 1.0a. Falls back to local queue."""

    def __init__(
        self,
        consumer_key=None,
        consumer_secret=None,
        access_token=None,
        access_token_secret=None,
        tweet_queue_dir=None,
    ):
        self.consumer_key = consumer_key
        self.consumer_secret = consumer_secret
        self.access_token = access_token
        self.access_token_secret = access_token_secret
        self.tweet_queue_dir = tweet_queue_dir or self._default_queue_dir()
        self._dry_run = not all(
            [consumer_key, consumer_secret, access_token, access_token_secret]
        )
        os.makedirs(self.tweet_queue_dir, exist_ok=True)

    @staticmethod
    def _default_queue_dir():
        return str(Path(__file__).resolve().parent / "data" / "tweet_queue")

    def post_tweet(self, text, media_path=None):
        if self._dry_run or not self.consumer_key:
            return self._save_for_manual(text, media_path)

        url = "https://api.twitter.com/2/tweets"
        payload = {"text": text}
        auth = _build_oauth_header(
            "POST",
            url,
            payload,
            self.consumer_key,
            self.consumer_secret,
            self.access_token,
            self.access_token_secret,
        )
        try:
            resp = requests.post(
                url,
                json=payload,
                headers={
                    "Authorization": auth,
                    "Content-Type": "application/json",
                },
                timeout=15,
            )
            if resp.status_code in (200, 201):
                data = resp.json()
                tid = data.get("data", {}).get("id", "unknown")
                logger.info("Tweet posted — id: %s", tid)
                return {"status": "success", "id": tid}
            logger.error("Twitter API %s: %s", resp.status_code, resp.text)
            return self._save_for_manual(text, media_path, reason=f"HTTP {resp.status_code}")
        except requests.RequestException as exc:
            logger.error("Twitter request failed: %s", exc)
            return self._save_for_manual(text, media_path, reason=str(exc))

    def _save_for_manual(self, text, media_path=None, reason="dry-run"):
        entry = {
            "text": text,
            "media_path": media_path,
            "created_at": datetime.datetime.utcnow().isoformat(),
            "reason": reason,
        }
        filename = f"tweet_{int(time.time())}_{random.randint(100,999)}.json"
        filepath = os.path.join(self.tweet_queue_dir, filename)
        with open(filepath, "w") as f:
            json.dump(entry, f, indent=2)
        logger.info("Tweet queued: %s (reason: %s)", filepath, reason)
        return {"status": "queued", "file": filepath}


# ── Reddit Auto-Scraper ─────────────────────────────────────────────


def scrape_trending(subreddits=None, limit=10, client_id=None, client_secret=None, user_agent=None):
    """
    Fetch top hot posts from target subreddits (read-only).
    Returns list of {title, body, subreddit, score, comments, url}.
    """
    if not _HAVE_PRAW:
        logger.error("scrape_trending requires praw — install with: pip install praw")
        return []

    import praw

    subreddits = subreddits or [
        "Entrepreneur",
        "SideProject",
        "SaaS",
        "digital_marketing",
        "startups",
    ]
    reddit = praw.Reddit(
        client_id=client_id or os.environ.get("REDDIT_CLIENT_ID", ""),
        client_secret=client_secret or os.environ.get("REDDIT_CLIENT_SECRET", ""),
        user_agent=user_agent or "faceless-scraper/1.0",
    )
    results = []
    for name in subreddits:
        try:
            sub = reddit.subreddit(name)
            for post in sub.hot(limit=limit):
                results.append(
                    {
                        "title": post.title,
                        "body": post.selftext,
                        "subreddit": name,
                        "score": post.score,
                        "comments": post.num_comments,
                        "url": post.url,
                    }
                )
        except Exception as exc:
            logger.warning("Failed to scrape r/%s: %s", name, exc)
    logger.info("Scraped %d posts from %d subreddits", len(results), len(subreddits))
    return results


# ── Distribution Cycle ───────────────────────────────────────────────


def run_distribution_cycle(content_dir, platforms_config=None, reddit_dist=None, twitter_dist=None):
    """
    Scan content_dir for new JSON files and distribute to each enabled platform.
    Returns a dict mapping file path -> per-platform results.
    """
    from distribution.platforms_config import PLATFORMS

    config = platforms_config or PLATFORMS
    content_path = Path(content_dir)

    if not content_path.exists():
        logger.warning("Content directory not found: %s", content_dir)
        return {}

    json_files = sorted(content_path.glob("*.json"))
    if not json_files:
        logger.info("No content files in %s", content_dir)
        return {}

    overall = {}
    for fp in json_files:
        try:
            with open(fp, "r", encoding="utf-8") as f:
                content = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("Skipping %s: %s", fp, exc)
            overall[str(fp)] = {"status": "error", "error": str(exc)}
            continue

        entry = {"file": str(fp), "platforms": {}}
        title = content.get("title", "")
        body = content.get("body") or content.get("text", "")

        # Reddit
        rc = config.get("reddit", {})
        if rc.get("enabled"):
            for sub in rc.get("target_subreddits", []):
                if reddit_dist:
                    res = reddit_dist.post_to_subreddit(sub, title, body)
                else:
                    res = {"status": "skipped", "reason": "no distributor"}
                entry["platforms"][f"reddit:{sub}"] = res

        # Twitter
        tc = config.get("twitter", {})
        if tc.get("enabled"):
            tweet_text = title
            if body:
                tweet_text = f"{title}\n\n{body}"
            tweet_text = tweet_text[:280]
            if twitter_dist:
                res = twitter_dist.post_tweet(tweet_text)
            else:
                res = {"status": "skipped", "reason": "no distributor"}
            entry["platforms"]["twitter"] = res

        # TikTok (manual script export)
        ttc = config.get("tiktok_manual", {})
        if ttc.get("enabled"):
            script_dir = Path(ttc.get("saved_scripts_dir", "../content/tiktok_scripts/"))
            script_dir.mkdir(parents=True, exist_ok=True)
            script_payload = {
                "source": str(fp),
                "title": title,
                "script": body,
                "hashtags": content.get("hashtags", []),
                "created_at": datetime.datetime.utcnow().isoformat(),
            }
            script_path = script_dir / f"{fp.stem}_script.json"
            with open(script_path, "w") as f:
                json.dump(script_payload, f, indent=2)
            entry["platforms"]["tiktok_manual"] = {"status": "saved", "path": str(script_path)}

        overall[str(fp)] = entry

        # Archive processed file
        processed = content_path / "processed"
        processed.mkdir(exist_ok=True)
        fp.rename(processed / fp.name)

    logger.info("Distribution cycle done — %d files processed", len(json_files))
    return overall
