"""
ETL Ledger Manager

This module provides functionality for managing the content ingestion ledger,
which tracks what content needs to be processed. The ledger is stored as
native JSON in Redis and supports CRUD operations for repositories, blogs,
and notebooks.

The ledger structure:
{
    "repos": [{"name": "...", "github_url": "..."}],
    "blogs": [{"name": "...", "blog_url": "..."}],
    "notebooks": [{"name": "...", "github_url": "..."}]
}
"""

import logging
from typing import Dict, List

from app.utilities.database import get_redis_client

logger = logging.getLogger(__name__)

# Redis key for the ETL ledger
ETL_LEDGER_KEY = "etl:content_ledger"


class ETLedgerManager:
    """
    Manages the ETL content ledger for tracking what content to ingest.

    This class provides methods to manage the content ledger stored in Redis,
    including adding, removing, and retrieving content items for processing.
    """

    def __init__(self) -> None:
        """Initialize the ETL ledger manager."""
        self.redis_client = None

    async def _get_redis_client(self):
        """
        Get Redis client, initializing if needed.

        Returns:
            Redis client instance
        """
        if self.redis_client is None:
            self.redis_client = get_redis_client()
        return self.redis_client

    async def get_ledger(self) -> Dict[str, List[Dict[str, str]]]:
        """
        Get the current content ledger from Redis.

        Returns:
            Dictionary with repos, blogs, and notebooks lists
        """
        client = await self._get_redis_client()

        try:
            ledger_data = await client.json().get(ETL_LEDGER_KEY)
            if ledger_data:
                return ledger_data
            else:
                # Return empty ledger structure
                return {"repos": [], "blogs": [], "notebooks": []}
        except Exception as e:
            logger.error(f"Failed to get ledger: {e}")
            raise

    async def update_ledger(self, ledger_data: Dict[str, List[Dict[str, str]]]) -> bool:
        """
        Update the content ledger in Redis.

        Args:
            ledger_data: Dictionary with repos, blogs, and notebooks lists

        Returns:
            True if successful
        """
        client = await self._get_redis_client()

        try:
            await client.json().set(ETL_LEDGER_KEY, "$", ledger_data)
            logger.info("Updated ETL ledger successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to update ledger: {e}")
            raise

    async def add_repo_to_ledger(self, repo_name: str, github_url: str) -> bool:
        """
        Add a repository to the ledger.

        Args:
            repo_name: Name of the repository
            github_url: GitHub URL of the repository

        Returns:
            True if successful
        """
        ledger = await self.get_ledger()

        # Check if repo already exists
        for repo in ledger["repos"]:
            if repo["name"] == repo_name:
                logger.warning(f"Repository {repo_name} already exists in ledger")
                return True

        # Add new repo
        ledger["repos"].append({"name": repo_name, "github_url": github_url})

        return await self.update_ledger(ledger)

    async def add_blog_to_ledger(self, blog_name: str, blog_url: str) -> bool:
        """
        Add a blog to the ledger.

        Args:
            blog_name: Name of the blog
            blog_url: URL of the blog

        Returns:
            True if successful
        """
        ledger = await self.get_ledger()

        # Check if blog already exists
        for blog in ledger["blogs"]:
            if blog["name"] == blog_name:
                logger.warning(f"Blog {blog_name} already exists in ledger")
                return True

        # Add new blog
        ledger["blogs"].append({"name": blog_name, "blog_url": blog_url})

        return await self.update_ledger(ledger)

    async def add_notebook_to_ledger(self, notebook_name: str, github_url: str) -> bool:
        """
        Add a notebook to the ledger.

        Args:
            notebook_name: Name of the notebook
            github_url: GitHub URL of the notebook

        Returns:
            True if successful
        """
        ledger = await self.get_ledger()

        # Check if notebook already exists
        for notebook in ledger["notebooks"]:
            if notebook["name"] == notebook_name:
                logger.warning(f"Notebook {notebook_name} already exists in ledger")
                return True

        # Add new notebook
        ledger["notebooks"].append({"name": notebook_name, "github_url": github_url})

        return await self.update_ledger(ledger)

    async def remove_repo_from_ledger(self, repo_name: str) -> bool:
        """
        Remove a repository from the ledger.

        Args:
            repo_name: Name of the repository to remove

        Returns:
            True if successful
        """
        ledger = await self.get_ledger()

        # Remove repo if it exists
        ledger["repos"] = [
            repo for repo in ledger["repos"] if repo["name"] != repo_name
        ]

        return await self.update_ledger(ledger)

    async def remove_blog_from_ledger(self, blog_name: str) -> bool:
        """
        Remove a blog from the ledger.

        Args:
            blog_name: Name of the blog to remove

        Returns:
            True if successful
        """
        ledger = await self.get_ledger()

        # Remove blog if it exists
        ledger["blogs"] = [
            blog for blog in ledger["blogs"] if blog["name"] != blog_name
        ]

        return await self.update_ledger(ledger)

    async def remove_notebook_from_ledger(self, notebook_name: str) -> bool:
        """
        Remove a notebook from the ledger.

        Args:
            notebook_name: Name of the notebook to remove

        Returns:
            True if successful
        """
        ledger = await self.get_ledger()

        # Remove notebook if it exists
        ledger["notebooks"] = [
            notebook
            for notebook in ledger["notebooks"]
            if notebook["name"] != notebook_name
        ]

        return await self.update_ledger(ledger)

    async def seed_ledger_with_sample_content(self) -> bool:
        """
        Seed the ledger with sample blogs and notebooks (no repos for now).

        Returns:
            True if successful
        """
        try:
            # Add sample blog to the ledger
            blog_success = await self.add_blog_to_ledger(
                blog_name="redis-quantization-dimensionality-reduction",
                blog_url="https://redis.io/blog/redis-quantization-dimensionality-reduction/",
            )

            # Add sample notebook to the ledger
            notebook_success = await self.add_notebook_to_ledger(
                notebook_name="02_hybrid_search",
                github_url="https://github.com/RedisVentures/redis-retrieval-optimizer/blob/main/notebooks/02_hybrid_search.ipynb",
            )

            if blog_success and notebook_success:
                logger.info(
                    "Successfully seeded ledger with sample blogs and notebooks"
                )
            else:
                logger.error("Failed to seed ledger with sample content")

            return blog_success and notebook_success

        except Exception as e:
            logger.error(f"Failed to seed ledger: {e}")
            raise


def get_etl_ledger_manager() -> ETLedgerManager:
    """Get ETL ledger manager instance."""
    return ETLedgerManager()
