"""
Simple tests for vectorization queries and logic.

This module tests the core functions used by the API for vectorization
with simple, focused tests on the most important logic.
"""

from unittest.mock import Mock, patch

import pytest


class TestVectorizationQueriesSimple:
    """Simple test cases for vectorization query functions."""

    def test_build_file_info_from_tracking_record(self):
        """Test building file info from tracking record."""
        from app.etl.vectorization_queries import build_file_info_from_tracking_record

        tracking_record = {
            "name": "test-content",
            "content_type": "blog",
            "bucket_url": "s3://test-bucket/processed/blog_text/2025-09-10/test-content.md",
            "source_date": "2025-09-10",
        }

        result = build_file_info_from_tracking_record(tracking_record)

        # Verify the file info is built correctly
        assert result["s3_key"] == "processed/blog_text/2025-09-10/test-content.md"
        assert result["filename"] == "test-content.md"
        assert result["content_type"] == "blog"
        assert result["date_folder"] == "2025-09-10"

    def test_build_file_info_with_repo_content(self):
        """Test building file info for repo content (PDF)."""
        from app.etl.vectorization_queries import build_file_info_from_tracking_record

        tracking_record = {
            "name": "my-repo",
            "content_type": "repo",
            "bucket_url": "s3://test-bucket/processed/repo/2025-09-10/my-repo.pdf",
            "source_date": "2025-09-10",
        }

        result = build_file_info_from_tracking_record(tracking_record)

        # Verify the file info is built correctly for PDF
        assert result["s3_key"] == "processed/repo/2025-09-10/my-repo.pdf"
        assert result["filename"] == "my-repo.pdf"
        assert result["content_type"] == "repo"
        assert result["date_folder"] == "2025-09-10"

    def test_build_file_info_invalid_bucket_url(self):
        """Test building file info with invalid bucket URL."""
        from app.etl.vectorization_queries import build_file_info_from_tracking_record

        tracking_record = {
            "name": "test-content",
            "content_type": "blog",
            "bucket_url": "invalid-url",
            "source_date": "2025-09-10",
        }

        with pytest.raises(ValueError, match="Invalid bucket URL"):
            build_file_info_from_tracking_record(tracking_record)

    def test_build_file_info_malformed_s3_url(self):
        """Test building file info with malformed S3 URL."""
        from app.etl.vectorization_queries import build_file_info_from_tracking_record

        tracking_record = {
            "name": "test-content",
            "content_type": "blog",
            "bucket_url": "s3://bucket-only",  # Missing path
            "source_date": "2025-09-10",
        }

        with pytest.raises(ValueError, match="Invalid S3 URL format"):
            build_file_info_from_tracking_record(tracking_record)

    @patch("app.etl.vectorization_queries.boto3.client")
    @pytest.mark.asyncio
    async def test_get_latest_date_folder_blog(self, mock_boto_client):
        """Test finding the latest date folder for blog content."""
        from app.etl.vectorization_queries import get_latest_date_folder

        # Mock S3 client response for blog content
        mock_s3_client = Mock()
        mock_boto_client.return_value = mock_s3_client

        mock_response = {
            "CommonPrefixes": [
                {"Prefix": "processed/blog_text/2025-09-08/"},
                {"Prefix": "processed/blog_text/2025-09-10/"},
                {"Prefix": "processed/blog_text/2025-09-09/"},
            ]
        }
        mock_s3_client.list_objects_v2.return_value = mock_response

        # Test the function
        result = await get_latest_date_folder("test-bucket", "blog")

        # Should return the latest date (sorted)
        assert result == "2025-09-10"

        # Verify S3 was called with correct prefix for blog
        mock_s3_client.list_objects_v2.assert_called_once_with(
            Bucket="test-bucket", Prefix="processed/blog_text/", Delimiter="/"
        )

    @patch("app.etl.vectorization_queries.boto3.client")
    @pytest.mark.asyncio
    async def test_get_latest_date_folder_repo(self, mock_boto_client):
        """Test finding the latest date folder for repo content."""
        from app.etl.vectorization_queries import get_latest_date_folder

        # Mock S3 client response for repo content
        mock_s3_client = Mock()
        mock_boto_client.return_value = mock_s3_client

        mock_response = {
            "CommonPrefixes": [
                {"Prefix": "processed/repo/2025-09-09/"},
                {"Prefix": "processed/repo/2025-09-11/"},
            ]
        }
        mock_s3_client.list_objects_v2.return_value = mock_response

        # Test the function
        result = await get_latest_date_folder("test-bucket", "repo")

        # Should return the latest date
        assert result == "2025-09-11"

        # Verify S3 was called with correct prefix for repo
        mock_s3_client.list_objects_v2.assert_called_once_with(
            Bucket="test-bucket", Prefix="processed/repo/", Delimiter="/"
        )

    @patch("app.etl.vectorization_queries.boto3.client")
    @pytest.mark.asyncio
    async def test_list_content_files_in_s3_folder_blog(self, mock_boto_client):
        """Test listing blog content files (markdown) in S3 folder."""
        from app.etl.vectorization_queries import list_content_files_in_s3_folder

        # Mock S3 client response
        mock_s3_client = Mock()
        mock_boto_client.return_value = mock_s3_client

        mock_response = {
            "Contents": [
                {"Key": "processed/blog_text/2025-09-10/blog1.md"},
                {"Key": "processed/blog_text/2025-09-10/blog2.md"},
                {
                    "Key": "processed/blog_text/2025-09-10/other.txt"
                },  # Should be filtered out
                {
                    "Key": "processed/blog_text/2025-09-10/subfolder/"
                },  # Directory, filtered out
            ]
        }
        mock_s3_client.list_objects_v2.return_value = mock_response

        # Test the function
        result = await list_content_files_in_s3_folder(
            "test-bucket", "blog", "2025-09-10"
        )

        # Should only return .md files
        assert len(result) == 2
        assert result[0]["filename"] == "blog1.md"
        assert result[0]["s3_key"] == "processed/blog_text/2025-09-10/blog1.md"
        assert result[0]["content_type"] == "blog"
        assert result[0]["date_folder"] == "2025-09-10"

        assert result[1]["filename"] == "blog2.md"
        assert result[1]["s3_key"] == "processed/blog_text/2025-09-10/blog2.md"

    @patch("app.etl.vectorization_queries.boto3.client")
    @pytest.mark.asyncio
    async def test_list_content_files_in_s3_folder_repo(self, mock_boto_client):
        """Test listing repo content files (PDF) in S3 folder."""
        from app.etl.vectorization_queries import list_content_files_in_s3_folder

        # Mock S3 client response
        mock_s3_client = Mock()
        mock_boto_client.return_value = mock_s3_client

        mock_response = {
            "Contents": [
                {"Key": "processed/repo/2025-09-10/repo1.pdf"},
                {"Key": "processed/repo/2025-09-10/repo2.pdf"},
                {
                    "Key": "processed/repo/2025-09-10/readme.md"
                },  # Should be filtered out for repo
            ]
        }
        mock_s3_client.list_objects_v2.return_value = mock_response

        # Test the function
        result = await list_content_files_in_s3_folder(
            "test-bucket", "repo", "2025-09-10"
        )

        # Should only return .pdf files for repo content
        assert len(result) == 2
        assert result[0]["filename"] == "repo1.pdf"
        assert result[0]["content_type"] == "repo"
        assert result[1]["filename"] == "repo2.pdf"
