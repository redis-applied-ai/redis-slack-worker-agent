import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import boto3
from botocore.exceptions import ClientError, NoCredentialsError

from app.utilities.environment import get_env_var

logger = logging.getLogger(__name__)

# S3 Configuration constants
S3_BUCKET_PREFIX = "applied-ai-agent"
S3_REGION = "us-east-2"


def get_s3_bucket_name() -> str:
    """
    Get S3 bucket name based on environment.

    Returns:
        S3 bucket name in format: {environment}-{bucket_prefix}
    """
    env = get_env_var("ENVIRONMENT", "dev")
    return f"{env}-{S3_BUCKET_PREFIX}"


class S3Manager:
    """Simple S3 manager for evaluation results"""

    def __init__(self, bucket_name: str = "applied-ai-agent"):
        self.bucket_name = bucket_name
        try:
            self.s3_client = boto3.client("s3")
            self.s3_client.head_bucket(Bucket=bucket_name)
        except Exception as e:
            logger.error(f"S3 connection failed: {e}")
            raise

    def load_test_cases(self) -> List[Dict[str, Any]]:
        """Load test cases from S3"""
        try:
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key=os.environ.get(
                    "S3_EVAL_TEST_CASE_PATH",
                    "evaluations/test_cases/agent_behavior_test_cases.json",
                ),
            )
            return json.loads(response["Body"].read().decode("utf-8"))
        except Exception as e:
            logger.error(f"Failed to load test cases from S3: {e}")
            return []

    def save_results(self, results: Dict[str, Any]) -> str:
        """Save evaluation results to S3"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        key = f"evaluations/{timestamp}_eval.json"

        try:
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=json.dumps(results, indent=2, default=str),
                ContentType="application/json",
            )
            return key
        except Exception as e:
            logger.error(f"Failed to save results to S3: {e}")
            raise

    def get_trends(self, days: int = 30) -> Dict[str, Any]:
        """Get simple trends from recent evaluations"""
        try:
            # List recent evaluation files
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name, Prefix="evaluations/", MaxKeys=100
            )

            if "Contents" not in response:
                return {"error": "No evaluation results found"}

            # Get recent results
            cutoff_date = datetime.now() - timedelta(days=days)
            cutoff_date = cutoff_date.replace(hour=0, minute=0, second=0, microsecond=0)

            recent_results = []
            for obj in response["Contents"]:
                if obj["Key"].endswith("_eval.json"):
                    try:
                        result = self.s3_client.get_object(
                            Bucket=self.bucket_name, Key=obj["Key"]
                        )
                        data = json.loads(result["Body"].read().decode("utf-8"))
                        recent_results.append(data)
                    except Exception:
                        continue

            if not recent_results:
                return {"error": f"No results found in last {days} days"}

            # Calculate simple trends
            scores = [
                r.get("summary", {}).get("weighted_avg_score", 0)
                for r in recent_results
            ]
            pass_rates = [
                r.get("summary", {}).get("pass_rate", 0) for r in recent_results
            ]

            return {
                "total_evaluations": len(recent_results),
                "avg_score": sum(scores) / len(scores),
                "avg_pass_rate": sum(pass_rates) / len(pass_rates),
                "score_trend": (
                    "improving"
                    if scores[-1] > sum(scores[:-1]) / len(scores[:-1])
                    else "declining"
                ),
                "pass_rate_trend": (
                    "improving"
                    if pass_rates[-1] > sum(pass_rates[:-1]) / len(pass_rates[:-1])
                    else "declining"
                ),
            }

        except Exception as e:
            logger.error(f"Failed to get trends: {e}")
            return {"error": str(e)}


def get_s3_manager() -> Optional[S3Manager]:
    """Get S3 manager if configured"""
    try:
        return S3Manager()
    except (ClientError, NoCredentialsError) as e:
        logger.error(f"Failed to initialize S3Manager: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error in get_s3_manager: {e}")
        return None
