"""
Faceless System — Orchestrator
Single entry point for the entire faceless content automation system.
"""

import argparse
import json
import logging
import os
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from engine.content_generator import run_pipeline
from engine.demand_fusion import DemandFusionEngine
from distribution.distributor import run_distribution_cycle
from analytics.multiplier import PerformanceTracker, MultiplierLoop, run_amplify_cycle

try:
    from offer.landing import app as flask_app, load_leads, load_stats
    HAS_FLASK = True
except ModuleNotFoundError:
    HAS_FLASK = False

    def load_leads():
        return []

    def load_stats():
        return {"total_leads": 0, "total_content_generated": 0, "total_posts": 0}

logger = logging.getLogger("orchestrator")
logger.setLevel(logging.INFO)
_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(
    logging.Formatter("%(asctime)s  %(levelname)-8s  %(message)s", datefmt="%H:%M:%S")
)
logger.handlers.clear()
logger.addHandler(_handler)

ROOT = Path(__file__).resolve().parent

REQUIRED_DIRS = ["engine", "distribution", "offer", "analytics", "content", "deploy"]
DATA_DIRS = [
    "engine/data",
    "distribution/data",
    "offer/data",
    "analytics/data",
    "content/processed",
    "content/tiktok_scripts",
]


class FacelessEngine:
    """Orchestrates trend detection, content generation, distribution, and analytics."""

    def __init__(self):
        self.root = ROOT
        self._validate_dirs()
        self._create_data_dirs()

        self.fusion = DemandFusionEngine(data_dir=str(ROOT / "engine" / "data"))
        self.tracker = PerformanceTracker()
        self.multiplier = MultiplierLoop(
            tracker=self.tracker, fusion_engine=self.fusion
        )
        self._server_thread: threading.Thread | None = None
        self._bootstrap_count = 0

        self.tracker.load_state()
        logger.info("FacelessEngine initialized — root=%s", self.root)

    def _validate_dirs(self):
        missing = [d for d in REQUIRED_DIRS if not (self.root / d).is_dir()]
        if missing:
            logger.warning("Missing expected directories: %s", ", ".join(missing))

    def _create_data_dirs(self):
        for d in DATA_DIRS:
            (self.root / d).mkdir(parents=True, exist_ok=True)

    def bootstrap(self) -> dict:
        """Run one full lifecycle: detect trends, generate, distribute, track, amplify."""
        logger.info("")
        logger.info("=" * 60)
        logger.info("  BOOTSTRAP CYCLE %d", self._bootstrap_count + 1)
        logger.info("=" * 60)

        report = self.fusion.run_cycle()
        generated = report.get("generated", [])

        dist_result = {}
        if generated:
            try:
                content_dir = self.root / "content"
                dist_result = run_distribution_cycle(str(content_dir))
                logger.info("Distribution: %d files processed", len(dist_result))
            except Exception as exc:
                logger.error("Distribution failed: %s", exc)
        else:
            logger.warning("No content generated — skipping distribution")

        for g in generated:
            topic = g.get("topic", "unknown")
            post_id = f"bootstrap_{self._bootstrap_count}_{topic[:20].replace(' ', '_')}"
            self.tracker.track_post(
                post_id=post_id,
                platform="auto",
                topic=topic,
                content_hash=g.get("file", ""),
            )

        amp_result = {}
        try:
            amp_result = run_amplify_cycle(
                tracker=self.tracker, fusion_engine=self.fusion
            )
            if amp_result.get("amplified_pieces", 0):
                logger.info(
                    "Amplified %d pieces from winners",
                    amp_result["amplified_pieces"],
                )
        except Exception as exc:
            logger.error("Multiplier cycle failed: %s", exc)

        self._bootstrap_count += 1
        self._print_summary(report, dist_result, amp_result)

        return {"fusion": report, "distribution": dist_result, "multiplier": amp_result}

    def _print_summary(self, report: dict, dist: dict, amp: dict):
        gen = report.get("generated", [])
        print()
        print("=" * 60)
        print("  BOOTSTRAP SUMMARY")
        print("=" * 60)
        print(f"  Cycle:            {report.get('cycle_id', '?')}")
        print(f"  Trends scanned:   {report.get('trends_scanned', 0)}")
        print(f"  Topics scored:    {report.get('topics_scored', 0)}")
        print(f"  Content files:    {report.get('generated_count', 0)}")
        print(f"  Distribution:     {len(dist)} files")
        print(f"  Winners found:    {amp.get('winners_found', 0)}")
        print(f"  Amplified:        {amp.get('amplified_pieces', 0)} pieces")
        print(f"  Spikes detected:  {amp.get('spikes_detected', 0)}")
        print()
        print("  Top scores:")
        for ts in report.get("top_scores", []):
            print(
                f"    {ts.get('score', 0):5.1f}  [{ts.get('source', '?')}]  {ts.get('title', '?')[:70]}"
            )
        if gen:
            print()
            print("  Generated files:")
            for g in gen:
                print(f"    - {g.get('file', '?')}  (score: {g.get('score', 0)})")
        print("=" * 60)

    def start_server(self):
        """Launch Flask landing page in a daemon thread."""
        if not HAS_FLASK:
            logger.warning("Flask not installed — skipping server start. Run: pip install flask")
            return
        if self._server_thread and self._server_thread.is_alive():
            logger.info("Flask server already running")
            return

        port = int(os.environ.get("PORT", 5000))

        def _run():
            flask_app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

        self._server_thread = threading.Thread(
            target=_run, daemon=True, name="FlaskServer"
        )
        self._server_thread.start()
        logger.info("Flask server started on port %d", port)

    def start_multiplier(self):
        """Start multiplier loop in a daemon thread."""
        self.multiplier.start()

    def run_full(self):
        """Full mode: boot server + multiplier, run bootstrap, then loop."""
        logger.info("Starting Faceless Engine — full mode")
        self.start_server()
        self.start_multiplier()
        time.sleep(2)

        self.bootstrap()

        bootstrap_interval = 4 * 3600
        multiplier_interval = 30 * 60
        last_bootstrap = time.time()
        last_multiplier = time.time()

        try:
            while True:
                now = time.time()

                if now - last_bootstrap >= bootstrap_interval:
                    self.bootstrap()
                    last_bootstrap = now

                if now - last_multiplier >= multiplier_interval:
                    logger.info("Multiplier check cycle...")
                    try:
                        result = run_amplify_cycle(
                            tracker=self.tracker, fusion_engine=self.fusion
                        )
                        if result.get("amplified_pieces", 0):
                            logger.info(
                                "Amplified %d new pieces",
                                result["amplified_pieces"],
                            )
                    except Exception as exc:
                        logger.error("Multiplier check failed: %s", exc)
                    last_multiplier = now

                time.sleep(60)
        except KeyboardInterrupt:
            logger.info("Shutdown signal received")
            self.multiplier.stop()
            logger.info("Faceless Engine stopped")

    def status(self) -> dict:
        """Print and return current system state."""
        leads = []
        stats = {"total_leads": 0, "total_content_generated": 0, "total_posts": 0}
        try:
            leads = load_leads()
            stats = load_stats()
        except Exception:
            pass

        posts = self.tracker.all_posts()
        winners = self.tracker.get_winners()

        total_clicks = sum(w.get("clicks", 0) for w in winners)
        est_revenue = int(total_clicks * 0.09 * 47)

        print()
        print("=" * 60)
        print("  FACELESS ENGINE — STATUS")
        print("=" * 60)
        print(f"  Leads captured:       {stats.get('total_leads', 0)}")
        print(f"  Posts tracked:        {len(posts)}")
        print(f"  Winning posts:        {len(winners)}")
        print(f"  Bootstrap cycles run: {self._bootstrap_count}")
        print(
            f"  Server running:       {self._server_thread is not None and self._server_thread.is_alive()}"
        )
        print(f"  Multiplier active:    {self.multiplier.active}")
        print(f"  Est. revenue:         ${est_revenue}")
        print("=" * 60)

        return {
            "leads": len(leads),
            "posts_tracked": len(posts),
            "winners": len(winners),
            "bootstrap_cycles": self._bootstrap_count,
            "server_running": self._server_thread.is_alive()
            if self._server_thread
            else False,
            "multiplier_active": self.multiplier.active,
            "est_revenue_usd": est_revenue,
        }


def main():
    parser = argparse.ArgumentParser(description="Faceless Engine Orchestrator")
    parser.add_argument(
        "--mode", "-m",
        choices=["full", "bootstrap", "server", "status", "one-shot"],
        default="one-shot",
        help="Operating mode (default: one-shot)",
    )
    args = parser.parse_args()

    engine = FacelessEngine()

    if args.mode == "full":
        engine.run_full()
    elif args.mode == "bootstrap":
        engine.bootstrap()
    elif args.mode == "server":
        engine.start_server()
        logger.info("Landing page server running. Press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(10)
        except KeyboardInterrupt:
            logger.info("Server stopped.")
    elif args.mode == "status":
        engine.status()
    elif args.mode == "one-shot":
        result = engine.bootstrap()
        print()
        print("=" * 60)
        print("  ONE-SHOT COMPLETE")
        print(f"  Content generated: {result['fusion'].get('generated_count', 0)}")
        print(f"  Files distributed:  {len(result.get('distribution', {}))}")
        print(
            f"  Winners amplified:  {result.get('multiplier', {}).get('amplified_pieces', 0)}"
        )
        print(f"  Trends scored:      {result['fusion'].get('topics_scored', 0)}")
        print("=" * 60)


if __name__ == "__main__":
    main()
