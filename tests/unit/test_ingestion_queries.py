"""
Tests for ingestion queries and refresh logic.

This module tests the actual functions used by the API for querying
the knowledge tracking index and determining refresh policies.
"""

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch


class TestIngestionQueries:
    """Test cases for ingestion query functions."""

    def test_should_process_content_with_staged_status(self):
        """Test that staged content is always processed."""
        from app.etl.ingestion_queries import should_process_content

        content_item = {
            "name": "test-content",
            "processing_status": "staged",
            "source_date": "2025-09-10",
        }

        result = should_process_content(content_item)
        assert result is True

    def test_should_process_content_skips_currently_processing(self):
        """Test that content currently being processed is skipped."""
        from app.etl.ingestion_queries import should_process_content

        content_item = {
            "name": "test-content",
            "processing_status": "processing",
            "source_date": "2025-09-10",
        }

        result = should_process_content(content_item)
        assert result is False

    def test_should_process_content_skips_processing(self):
        """Test that content already processing is skipped."""
        from app.etl.ingestion_queries import should_process_content

        for status in ["processing", "ingest-pending", "vectorize-pending"]:
            content_item = {
                "name": "test-content",
                "processing_status": status,
                "source_date": "2025-09-10",
            }

            result = should_process_content(content_item)
            assert result is False, f"Status {status} should be skipped"

    def test_should_process_content_with_stale_date(self):
        """Test that stale content is processed based on CONTENT_REFRESH_THRESHOLD_DAYS."""
        from app.etl.ingestion_queries import should_process_content

        # Mock environment variable for 7-day threshold
        with patch.dict(os.environ, {"CONTENT_REFRESH_THRESHOLD_DAYS": "7"}):
            # Create content that is 10 days old (stale)
            stale_date = (datetime.now(timezone.utc) - timedelta(days=10)).strftime(
                "%Y-%m-%d"
            )

            content_item = {
                "name": "stale-content",
                "processing_status": "completed",  # Completed but stale
                "source_date": stale_date,
            }

            result = should_process_content(content_item)
            assert result is True

    def test_should_process_content_with_fresh_date(self):
        """Test that fresh content is not processed."""
        from app.etl.ingestion_queries import should_process_content

        # Mock environment variable for 7-day threshold
        with patch.dict(os.environ, {"CONTENT_REFRESH_THRESHOLD_DAYS": "7"}):
            # Create content that is 3 days old (fresh)
            fresh_date = (datetime.now(timezone.utc) - timedelta(days=3)).strftime(
                "%Y-%m-%d"
            )

            content_item = {
                "name": "fresh-content",
                "processing_status": "completed",  # Completed and fresh
                "source_date": fresh_date,
            }

            result = should_process_content(content_item)
            assert result is False

    def test_filter_content_by_type(self):
        """Test that content filtering by type works correctly."""
        from app.etl.ingestion_queries import filter_content_by_type

        content_items = [
            {"name": "blog1", "content_type": "blog"},
            {"name": "repo1", "content_type": "repo"},
            {"name": "blog2", "content_type": "blog"},
            {"name": "notebook1", "content_type": "notebook"},
        ]

        # Filter for blogs
        blog_items = filter_content_by_type(content_items, "blog")
        assert len(blog_items) == 2
        assert all(item["content_type"] == "blog" for item in blog_items)
        assert "blog1" in [item["name"] for item in blog_items]
        assert "blog2" in [item["name"] for item in blog_items]

        # Filter for repos
        repo_items = filter_content_by_type(content_items, "repo")
        assert len(repo_items) == 1
        assert repo_items[0]["name"] == "repo1"

    def test_build_ingestion_query(self):
        """Test that the ingestion query is built correctly."""
        from redis.commands.search.query import Query

        from app.etl.ingestion_queries import build_ingestion_query

        query = build_ingestion_query()

        # Verify the query object is created correctly
        assert query is not None
        assert isinstance(query, Query)
        # Verify it has the expected return fields
        assert query._return_fields is not None

    @patch("app.etl.ingestion_queries.redis.Redis")
    def test_query_content_for_ingestion(self, mock_redis_class):
        """Test the full query_content_for_ingestion function."""
        from app.etl.ingestion_queries import query_content_for_ingestion

        # Mock Redis client and search results
        mock_client = Mock()
        mock_redis_class.from_url.return_value = mock_client

        # Create mock search results with different statuses
        class MockDoc:
            def __init__(self, data):
                self.__dict__ = data

        mock_docs = [
            MockDoc(
                {
                    "name": "staged-content",
                    "content_type": "blog",
                    "processing_status": "staged",
                    "source_date": "2025-09-10",
                }
            ),
            MockDoc(
                {
                    "name": "completed-content",
                    "content_type": "blog",
                    "processing_status": "completed",
                    "source_date": "2025-09-10",
                }
            ),
        ]

        mock_search_results = Mock()
        mock_search_results.docs = mock_docs
        mock_client.ft.return_value.search.return_value = mock_search_results

        # Mock environment variable
        with patch.dict(os.environ, {"CONTENT_REFRESH_THRESHOLD_DAYS": "7"}):
            result = query_content_for_ingestion()

        # Verify both staged and completed content are returned (the function returns all content, filtering happens later)
        assert len(result) == 2
        # Check that staged content is included
        staged_content = next(
            (item for item in result if item["name"] == "staged-content"), None
        )
        assert staged_content is not None
        assert staged_content["processing_status"] == "staged"
        # Check that completed content is also included
        completed_content = next(
            (item for item in result if item["name"] == "completed-content"), None
        )
        assert completed_content is not None
        assert completed_content["processing_status"] == "completed"

        # Verify Redis was called correctly
        mock_redis_class.from_url.assert_called_once()
        mock_client.ft.assert_called_with("knowledge_tracking")
        mock_client.ft.return_value.search.assert_called_once()
