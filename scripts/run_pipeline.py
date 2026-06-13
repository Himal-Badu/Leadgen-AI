#!/usr/bin/env python3
"""Full Pipeline Runner — processes all pending snapshots end-to-end.

Usage:
    python scripts/run_pipeline.py [--once] [--max N]
"""
import logging
import sys
import time

from agents.scout import ScoutAgent
from agents.analyzer import AnalyzerAgent
from agents.scorer import ScoringAgent
from agents.strategist import StrategistAgent
from agents.builder import BuilderAgent


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def run_full_pipeline(max_per_stage: int = 10) -> dict[str, int]:
    """Run all four pipeline stages sequentially.
    
    Returns a dict with counts per stage.
    """
    results = {}

    # Stage 1: Scout
    logging.info("=== Stage 1: Scout Agent ===")
    scout = ScoutAgent()
    count = 0
    for _ in range(max_per_stage):
        r = scout.run_once()
        if r is None:
            break
        count += 1
    results["scout"] = count
    logging.info(f"Scout processed: {count}")

    # Stage 2: Analyzer
    logging.info("=== Stage 2: Analyzer Agent ===")
    analyzer = AnalyzerAgent()
    count = 0
    for _ in range(max_per_stage):
        r = analyzer.run_once()
        if r is None:
            break
        count += 1
    results["analyzer"] = count
    logging.info(f"Analyzer processed: {count}")

    # Stage 3: Scorer
    logging.info("=== Stage 3: Scoring Agent ===")
    scorer = ScoringAgent()
    count = 0
    for _ in range(max_per_stage):
        r = scorer.run_once()
        if r is None:
            break
        count += 1
    results["scorer"] = count
    logging.info(f"Scorer processed: {count}")

    # Stage 4: Strategist
    logging.info("=== Stage 4: Strategist Agent ===")
    strategist = StrategistAgent()
    count = 0
    for _ in range(max_per_stage):
        r = strategist.run_once()
        if r is None:
            break
        count += 1
    results["strategist"] = count
    logging.info(f"Strategist processed: {count}")

    # Stage 5: Builder
    logging.info("=== Stage 5: Builder Agent ===")
    builder = BuilderAgent()
    count = 0
    for _ in range(max_per_stage):
        r = builder.run_once()
        if r is None:
            break
        count += 1
    results["builder"] = count
    logging.info(f"Builder processed: {count}")

    return results


def main():
    import argparse
    parser = argparse.ArgumentParser(description="LocalPulse AI Pipeline Runner")
    parser.add_argument("--once", action="store_true", help="Only process one snapshot per stage")
    parser.add_argument("--max", type=int, default=10, help="Max snapshots per stage (default: 10)")
    parser.add_argument("--watch", action="store_true", help="Watch mode — poll continuously")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    args = parser.parse_args()

    setup_logging(args.verbose)

    max_per_stage = 1 if args.once else args.max

    if args.watch:
        logging.info("Starting watch mode (Ctrl+C to stop)...")
        try:
            while True:
                results = run_full_pipeline(max_per_stage=max_per_stage)
                total = sum(results.values())
                if total == 0:
                    logging.info("No work available, sleeping 10s...")
                    time.sleep(10)
                else:
                    logging.info(f"Batch complete: {results}")
        except KeyboardInterrupt:
            logging.info("Shutting down.")
    else:
        results = run_full_pipeline(max_per_stage=max_per_stage)
        total = sum(results.values())
        print(f"\nPipeline complete! Processed {total} snapshots total.")
        print(f"  Scout:      {results.get('scout', 0)}")
        print(f"  Analyzer:   {results.get('analyzer', 0)}")
        print(f"  Scorer:     {results.get('scorer', 0)}")
        print(f"  Strategist: {results.get('strategist', 0)}")
        print(f"  Builder:    {results.get('builder', 0)}")


if __name__ == "__main__":
    main()
