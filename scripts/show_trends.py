#!/usr/bin/env python3
"""
Simple script to show evaluation trends.

Usage:
    python scripts/show_trends.py
    python scripts/show_trends.py --days 7
"""

import argparse
import sys
from pathlib import Path

# Add the project root to the path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.s3_utils import get_s3_manager


def main():
    parser = argparse.ArgumentParser(description="Show evaluation trends")
    parser.add_argument(
        "--days", type=int, default=30, help="Number of days to analyze (default: 30)"
    )

    args = parser.parse_args()

    print("📊 Evaluation Trends")
    print("=" * 30)

    s3_manager = get_s3_manager()
    if not s3_manager:
        print("❌ S3 not available - check AWS credentials")
        return 1

    trends = s3_manager.get_trends(days=args.days)

    if "error" in trends:
        print(f"❌ {trends['error']}")
        return 1

    print(f"📈 Last {args.days} days:")
    print(f"   Evaluations: {trends['total_evaluations']}")
    print(f"   Avg Score: {trends['avg_score']:.1f}/10")
    print(f"   Avg Pass Rate: {trends['avg_pass_rate']:.1%}")
    print(f"   Score Trend: {trends['score_trend']}")
    print(f"   Pass Rate Trend: {trends['pass_rate_trend']}")

    return 0


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
