import asyncio
import json
import logging
import os
from typing import Any, Dict, List

import pytest

from app.agent import answer_question, get_client
from app.utilities.database import get_document_index, get_vectorizer
from app.utilities.s3_utils import get_s3_manager

logger = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def initialize_globals():
    """Initialize global vectorizer and index once for all tests to avoid concurrent initialization"""
    logger.info("Pre-initializing vectorizer and index for test session...")
    try:
        # Pre-warm the global instances
        vectorizer = get_vectorizer()
        index = get_document_index()
        logger.info("Global instances initialized successfully")
        return {"vectorizer": vectorizer, "index": index}
    except Exception as e:
        logger.error(f"Failed to initialize globals: {e}")
        pytest.fail(f"Could not initialize test dependencies: {e}")


class AgentBehaviorTestSuite:
    """Test suite for evaluating agent behavioral improvements"""

    def __init__(self):
        self.test_cases = self._load_test_cases()
        self.openai_client = get_client()

    def _load_test_cases(self) -> List[Dict[str, Any]]:
        """Load test cases covering different behavioral scenarios from S3 or local file."""
        # Try S3 first
        s3_manager = get_s3_manager()
        if s3_manager:
            test_cases = s3_manager.load_test_cases()
            if test_cases:
                logger.info("Loaded test cases from S3")
                return test_cases

        # Fallback to local file
        file_path = "tests/data/agent_behavior_test_cases.json"
        if not os.path.exists(file_path):
            logger.warning(
                f"Test cases file not found at {file_path}. Returning empty list."
            )
            return []
        try:
            with open(file_path, "r") as f:
                logger.info("Loaded test cases from local file")
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading test cases from {file_path}: {e}")
            return []

    async def run_test(
        self, test_case: Dict[str, Any], index=None, vectorizer=None
    ) -> Dict[str, Any]:
        """Run a single test case and return the result"""
        try:
            # Use provided instances or get global ones
            if index is None:
                index = get_document_index()
            if vectorizer is None:
                vectorizer = get_vectorizer()

            response = await answer_question(
                index=index,
                vectorizer=vectorizer,
                query=test_case["user_input"],
                session_id=f"test_session_{test_case.get('id', 'unknown')}",
                user_id="test_user",
                thread_context=test_case.get("thread_context"),
            )

            # Evaluate the response
            evaluation = await self._evaluate_response(test_case, response)

            logger.info(
                f"Evaluation for query: {test_case['user_input']}: {evaluation.get('score', 0)}"
            )

            return {
                "test_case": test_case,
                "response": response,
                "evaluation": evaluation,
                "passed": evaluation["score"] >= 7.0,  # 7/10 or better to pass
            }

        except Exception as e:
            logger.exception("Test failed with error")
            return {
                "test_case": test_case,
                "response": f"ERROR: {str(e)}",
                "evaluation": {"score": 0, "reasoning": f"Test failed with error: {e}"},
                "passed": False,
            }

    async def _evaluate_response(
        self, test_case: Dict[str, Any], response: str
    ) -> Dict[str, Any]:
        """Use GPT-4 to evaluate if the response meets behavioral expectations"""

        evaluation_prompt = f"""
Evaluate this AI agent response based on the expected behavior:

CATEGORY: {test_case["category"]}
USER INPUT: "{test_case["user_input"]}"
THREAD CONTEXT: {json.dumps(test_case.get("thread_context", []), indent=2)}
EXPECTED BEHAVIOR: {test_case["expected_behavior"]}

AGENT RESPONSE: "{response}"

EVALUATION CRITERIA:
1. **Helpfulness**: Does the response directly address the coworker's question with a direct and helpful answer?
2. **Tone**: Is the response brief, friendly, and constructive without being overly robotic?
3. **Promotional Balance**: Is it helpful first, promotional second? Avoids being pushy?
4. **Accuracy**: For tool questions, does it mention AI capabilities vs product features correctly?
5. **Use of sources**: For complex questions, does the agent provide sources that can be used to validate the answer?
6. **List Formatting**: Does the response avoid nested bullet points and use headers to organize information instead?

SPECIFIC GUIDELINES:
- Brief satisfied responses ("sure", "thanks") should get brief acknowledgments, NOT promotional recaps
- Agent tool questions should mention search_knowledge_base, web_search, NOT Redis products
- Simple factual questions should avoid promotional content
- Redis-relevant questions can naturally mention Redis
- General AI questions should clarify scope, not immediately promote Redis
- If you are highly unsure about an answer please say so and mention reaching out to a member of the applied ai team

LIST FORMATTING REQUIREMENTS:
- NEVER use nested bullet points (e.g., "• Main item\\n    • Sub-item" or "• Main item\\n        • Sub-sub-item")
- Instead, use headers to group related information (e.g., "#### Feature Category:\\n• Item 1\\n• Item 2")
- All bullet points should be at the same level (flat lists only)
- Use Unicode bullet (•) for all bullet points
- Organize complex information with descriptive headers followed by flat bullet lists


Rate the response 1-10 and provide reasoning in JSON format:

{{
    "score": <1-10>,
    "reasoning": "Detailed explanation of why this score was given",
    "meets_expectations": <true/false>,
    "key_issues": ["list", "of", "any", "problems"],
    "strengths": ["list", "of", "good", "aspects"]
}}
"""

        logger.info(f"Evaluating result for input: {test_case['user_input']}")
        try:
            evaluation_response = self.openai_client.chat.completions.create(
                model="gpt-4o",  # Use a good model for evaluation
                messages=[{"role": "user", "content": evaluation_prompt}],
                response_format={"type": "json_object"},
                temperature=0.1,
                seed=42,
            )

            return json.loads(evaluation_response.choices[0].message.content)

        except Exception as e:
            logger.exception("Evaluation failed")
            return {
                "score": 0,
                "reasoning": f"Evaluation failed: {str(e)}",
                "meets_expectations": False,
                "key_issues": ["evaluation_error"],
                "strengths": [],
            }

    async def run_full_suite(self, index=None, vectorizer=None) -> Dict[str, Any]:
        """Run all test cases and return comprehensive results"""
        results = []

        for test_case in self.test_cases:
            print(
                f"Running test: {test_case['category']} - {test_case['user_input'][:50]}..."
            )
            result = await self.run_test(test_case, index=index, vectorizer=vectorizer)
            results.append(result)

        # Calculate overall metrics
        total_tests = len(results)
        passed_tests = sum(1 for r in results if r["passed"])

        # Weighted average score
        total_weighted_score = sum(
            r["evaluation"]["score"] * r["test_case"]["weight"] for r in results
        )
        total_weight = sum(r["test_case"]["weight"] for r in results)
        weighted_avg_score = (
            total_weighted_score / total_weight if total_weight > 0 else 0
        )

        # Category breakdown
        category_results = {}
        for result in results:
            category = result["test_case"]["category"]
            if category not in category_results:
                category_results[category] = {"passed": 0, "total": 0, "scores": []}

            category_results[category]["total"] += 1
            if result["passed"]:
                category_results[category]["passed"] += 1
            category_results[category]["scores"].append(result["evaluation"]["score"])

        # Calculate category averages
        for category in category_results:
            scores = category_results[category]["scores"]
            category_results[category]["avg_score"] = (
                sum(scores) / len(scores) if scores else 0
            )
            category_results[category]["pass_rate"] = (
                category_results[category]["passed"]
                / category_results[category]["total"]
            )

        return {
            "summary": {
                "total_tests": total_tests,
                "passed_tests": passed_tests,
                "pass_rate": passed_tests / total_tests if total_tests > 0 else 0,
                "weighted_avg_score": weighted_avg_score,
            },
            "category_breakdown": category_results,
            "detailed_results": results,
            "recommendations": self._generate_recommendations(results),
        }

    def _generate_recommendations(self, results: List[Dict[str, Any]]) -> List[str]:
        """Generate improvement recommendations based on test results"""
        recommendations = []

        # Check for common failure patterns
        failed_results = [r for r in results if not r["passed"]]

        # Group failures by category
        category_failures = {}
        for result in failed_results:
            category = result["test_case"]["category"]
            if category not in category_failures:
                category_failures[category] = []
            category_failures[category].append(result)

        for category, failures in category_failures.items():
            if category == "brief_satisfied":
                recommendations.append(
                    f"Brief satisfied responses: {len(failures)} failures. Consider improving brief response detection or system prompt."
                )
            elif category == "agent_tools":
                recommendations.append(
                    f"Agent tools questions: {len(failures)} failures. Review tool description logic and system prompt clarity."
                )
            elif category == "simple_factual":
                recommendations.append(
                    f"Simple factual questions: {len(failures)} failures. Reduce promotional content in non-Redis contexts."
                )
            elif category == "list_formatting":
                recommendations.append(
                    f"List formatting: {len(failures)} failures. Agent is using nested bullet points instead of headers to organize information. Review system prompt formatting guidelines."
                )

        # Look for recurring issues in evaluation reasoning
        common_issues = {}
        for result in failed_results:
            issues = result["evaluation"].get("key_issues", [])
            for issue in issues:
                common_issues[issue] = common_issues.get(issue, 0) + 1

        if common_issues:
            top_issues = sorted(
                common_issues.items(), key=lambda x: x[1], reverse=True
            )[:3]
            recommendations.append(
                f"Most common issues: {', '.join([f'{issue} ({count} times)' for issue, count in top_issues])}"
            )

        return recommendations


# Convenience functions for testing
async def run_behavior_tests(index=None, vectorizer=None):
    """Run the full behavioral test suite"""
    suite = AgentBehaviorTestSuite()
    return await suite.run_full_suite(index=index, vectorizer=vectorizer)


def print_test_results(results: Dict[str, Any]):
    """Pretty print test results"""
    summary = results["summary"]

    print("\n" + "=" * 60)
    print("AGENT BEHAVIOR TEST RESULTS")
    print("=" * 60)

    print("\nOVERALL SUMMARY:")
    print(
        f"  Tests Passed: {summary['passed_tests']}/{summary['total_tests']} ({summary['pass_rate']:.1%})"
    )
    print(f"  Weighted Average Score: {summary['weighted_avg_score']:.1f}/10")

    print("\nCATEGORY BREAKDOWN:")
    for category, stats in results["category_breakdown"].items():
        print(
            f"  {category}: {stats['passed']}/{stats['total']} passed ({stats['pass_rate']:.1%}), avg score: {stats['avg_score']:.1f}"
        )

    print("\nRECOMMENDATIONS:")
    for rec in results["recommendations"]:
        print(f"  • {rec}")

    print("\nDETAILED FAILURES:")
    for result in results["detailed_results"]:
        if not result["passed"]:
            test_case = result["test_case"]
            eval_result = result["evaluation"]
            print(f"\n  FAILED: {test_case['category']} - '{test_case['user_input']}'")
            print(f"    Score: {eval_result['score']}/10")
            print(f"    Issues: {', '.join(eval_result.get('key_issues', []))}")
            print(f"    Response: {result['response'][:100]}...")


# Pytest integration
@pytest.mark.skip(reason="Skipping behavior tests for now")
@pytest.mark.asyncio
async def test_agent_behavior_suite(initialize_globals):
    """Pytest wrapper for the behavior test suite"""
    globals_dict = initialize_globals
    results = await run_behavior_tests(
        index=globals_dict["index"], vectorizer=globals_dict["vectorizer"]
    )

    # Assert overall pass rate is acceptable
    assert (
        results["summary"]["pass_rate"] >= 0.8
    ), f"Pass rate too low: {results['summary']['pass_rate']:.1%}"

    # Assert weighted average score is acceptable
    assert (
        results["summary"]["weighted_avg_score"] >= 7.0
    ), f"Average score too low: {results['summary']['weighted_avg_score']:.1f}"

    # Print results for manual review
    print_test_results(results)


if __name__ == "__main__":
    # Run tests standalone
    logger.info("Pre-initializing vectorizer and index...")
    vectorizer = get_vectorizer()
    index = get_document_index()
    logger.info("Running behavior tests...")
    results = asyncio.run(run_behavior_tests(index=index, vectorizer=vectorizer))
    print_test_results(results)
