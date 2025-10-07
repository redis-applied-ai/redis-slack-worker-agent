#!/usr/bin/env python3
"""
Script to evaluate agent behavioral improvements.

Usage:
    python scripts/evaluate_agent.py
    python scripts/evaluate_agent.py --save-results results.json
    python scripts/evaluate_agent.py --save-to-s3
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add the project root to the path so we can import from app
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import after path modification
from app.s3_utils import get_s3_manager  # noqa: E402
from tests.test_agent_behavior import print_test_results, run_behavior_tests  # noqa: E402


async def main():
    parser = argparse.ArgumentParser(
        description="Evaluate agent behavioral improvements"
    )
    parser.add_argument(
        "--save-results", type=str, help="Save detailed results to JSON file"
    )
    parser.add_argument("--save-to-s3", action="store_true", help="Save results to S3")
    parser.add_argument(
        "--quiet", action="store_true", help="Only print summary, not detailed failures"
    )
    parser.add_argument(
        "--category",
        type=str,
        help="Run tests for specific category only (brief_satisfied, agent_tools, simple_factual, redis_relevant, general_ai, edge_case)",
    )

    args = parser.parse_args()

    print("🧪 Running Agent Behavior Evaluation Suite...")
    print(
        "This will test the agent's responses to various scenarios and evaluate them with GPT-4.\n"
    )

    # Check S3 if requested
    s3_manager = None
    if args.save_to_s3:
        s3_manager = get_s3_manager()
        if s3_manager:
            print("✅ S3 integration enabled")
        else:
            print("⚠️  S3 not available - check AWS credentials")

    try:
        results = await run_behavior_tests()

        # Filter by category if specified
        if args.category:
            filtered_results = []
            for result in results["detailed_results"]:
                if result["test_case"]["category"] == args.category:
                    filtered_results.append(result)

            if not filtered_results:
                print(f"❌ No tests found for category: {args.category}")
                print(
                    "Available categories: brief_satisfied, agent_tools, simple_factual, redis_relevant, general_ai, edge_case"
                )
                return

            # Recalculate summary for filtered results
            results["detailed_results"] = filtered_results
            results["summary"]["total_tests"] = len(filtered_results)
            results["summary"]["passed_tests"] = sum(
                1 for r in filtered_results if r["passed"]
            )
            results["summary"]["pass_rate"] = (
                results["summary"]["passed_tests"] / results["summary"]["total_tests"]
            )

            print(f"🔍 Showing results for category: {args.category}")

        # Print results (with option to hide detailed failures)
        if args.quiet:
            summary = results["summary"]
            print(
                f"✅ Tests Passed: {summary['passed_tests']}/{summary['total_tests']} ({summary['pass_rate']:.1%})"
            )
            print(f"📊 Weighted Average Score: {summary['weighted_avg_score']:.1f}/10")
        else:
            print_test_results(results)

        # Save detailed results if requested
        if args.save_results:
            with open(args.save_results, "w") as f:
                json.dump(results, f, indent=2, default=str)
            print(f"\n💾 Detailed results saved to: {args.save_results}")

        # Save to S3 if requested and available
        if args.save_to_s3 and s3_manager:
            try:
                s3_key = s3_manager.save_results(results)
                print(f"\n☁️  Results saved to S3: {s3_key}")
            except Exception as e:
                print(f"\n❌ Failed to save to S3: {e}")

        # Exit with appropriate code
        if results["summary"]["pass_rate"] >= 0.8:
            print("\n🎉 Agent behavior evaluation PASSED!")
            return 0
        else:
            print("\n❌ Agent behavior evaluation FAILED - needs improvement")
            return 1

    except Exception as e:
        print(f"❌ Error running evaluation: {e}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
