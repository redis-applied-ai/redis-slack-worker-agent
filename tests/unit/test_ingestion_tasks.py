"""
Tests for ETL ingestion tasks.

This module tests the ingestion functionality including:
- Blog processing (HTML to markdown)
- Notebook processing (Jupyter to markdown)
- Repository processing (GitHub to PDF)
- Tracking index updates
"""

from unittest.mock import AsyncMock, Mock, mock_open, patch

import pytest

from app.etl.tasks.ingestion import (
    get_s3_bucket_name,
    process_blog,
    process_notebook,
    process_repository,
    update_tracking_index,
)


class TestIngestionTasks:
    """Test cases for ingestion tasks."""

    @pytest.fixture
    def mock_storage_manager(self):
        """Mock S3 storage manager."""
        manager = AsyncMock()
        manager.upload_file.return_value = (
            "https://s3.amazonaws.com/bucket/test-file.md"
        )
        return manager

    @pytest.fixture
    def mock_redis_client(self):
        """Mock Redis client."""
        client = AsyncMock()
        json_mock = AsyncMock()
        json_mock.set = AsyncMock()
        client.json = Mock(return_value=json_mock)
        return client

    @pytest.fixture
    def sample_html_content(self):
        """Sample HTML content for testing."""
        return """
        <!DOCTYPE html>
        <html>
        <head><title>Test Blog</title></head>
        <body>
            <article>
                <h1>Test Blog Post</h1>
                <p>This is a test blog post content.</p>
                <h2>Section 1</h2>
                <p>More content here.</p>
            </article>
        </body>
        </html>
        """

    @pytest.fixture
    def sample_notebook_content(self):
        """Sample Jupyter notebook content for testing."""
        return {
            "cells": [
                {
                    "cell_type": "markdown",
                    "source": ["# Test Notebook\n", "This is a test notebook."],
                },
                {
                    "cell_type": "code",
                    "source": ["print('Hello, World!')"],
                    "outputs": [],
                },
            ],
            "metadata": {},
            "nbformat": 4,
            "nbformat_minor": 0,
        }

    def test_get_s3_bucket_name(self):
        """Test S3 bucket name generation."""
        with patch("app.utilities.s3_utils.get_env_var", return_value="test"):
            bucket_name = get_s3_bucket_name()
            assert bucket_name == "test-applied-ai-agent"

    @pytest.mark.asyncio
    async def test_update_tracking_index_success(self, mock_redis_client):
        """Test successful tracking index update."""
        # Mock that no existing record exists, so a new one will be created
        mock_redis_client.json.return_value.get = AsyncMock(return_value=None)

        with patch(
            "app.utilities.database.get_redis_client", return_value=mock_redis_client
        ):
            result = await update_tracking_index(
                "test-content", "blog_md", "https://s3.amazonaws.com/bucket/test.md"
            )

            assert result is True
            mock_redis_client.json.return_value.set.assert_called_once()

            # Check the call arguments
            call_args = mock_redis_client.json.return_value.set.call_args
            assert call_args[0][0] == "knowledge_tracking:test-content"
            assert call_args[0][1] == "$"

            tracking_record = call_args[0][2]
            assert tracking_record["name"] == "test-content"
            assert tracking_record["content_type"] == "blog_md"
            assert (
                tracking_record["bucket_url"]
                == "https://s3.amazonaws.com/bucket/test.md"
            )

    @pytest.mark.asyncio
    async def test_update_tracking_index_failure(self, mock_redis_client):
        """Test tracking index update failure."""
        mock_redis_client.json.return_value.set.side_effect = Exception("Redis error")

        with patch(
            "app.utilities.database.get_redis_client", return_value=mock_redis_client
        ):
            result = await update_tracking_index(
                "test-content", "blog_md", "https://s3.amazonaws.com/bucket/test.md"
            )

            assert result is False

    @pytest.mark.asyncio
    async def test_process_blog_success(
        self, mock_storage_manager, sample_html_content
    ):
        """Test successful blog processing."""
        with (
            patch(
                "app.etl.tasks.ingestion.get_s3_bucket_name", return_value="test-bucket"
            ),
            patch(
                "app.etl.tasks.ingestion.get_storage_manager",
                return_value=mock_storage_manager,
            ),
            patch("app.etl.tasks.ingestion.update_tracking_index", return_value=True),
            patch(
                "builtins.open", mock_open(read_data=sample_html_content)
            ) as mock_file,
            patch("aiohttp.ClientSession") as mock_aiohttp,
            patch("bs4.BeautifulSoup") as mock_bs,
            patch("markdownify.markdownify") as mock_markdownify,
        ):
            # Mock aiohttp response
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.read = AsyncMock(return_value=sample_html_content.encode())

            # Create proper async context manager for the response
            class MockResponseContextManager:
                def __init__(self, response):
                    self.response = response

                async def __aenter__(self):
                    return self.response

                async def __aexit__(self, exc_type, exc_val, exc_tb):
                    return None

            # Mock the session
            mock_session = AsyncMock()
            mock_session.get = Mock(
                return_value=MockResponseContextManager(mock_response)
            )

            # Mock the ClientSession context manager
            class MockSessionContextManager:
                def __init__(self, session):
                    self.session = session

                async def __aenter__(self):
                    return self.session

                async def __aexit__(self, exc_type, exc_val, exc_tb):
                    return None

            mock_aiohttp.return_value = MockSessionContextManager(mock_session)

            # Mock BeautifulSoup
            mock_soup = Mock()
            mock_soup.select_one.return_value = Mock()
            mock_soup.find.return_value = Mock()
            mock_bs.return_value = mock_soup

            # Mock markdownify
            mock_markdownify.return_value = (
                "# Test Blog Post\n\nThis is a test blog post content."
            )

            result = await process_blog("test-blog", "https://example.com/test-blog")

            assert result["status"] == "success"
            assert result["blog_name"] == "test-blog"
            assert "s3_url" in result
            assert "markdown_path" in result

    @pytest.mark.asyncio
    async def test_process_blog_http_error(self, sample_html_content):
        """Test blog processing with HTTP error."""
        with (
            patch(
                "app.etl.tasks.ingestion.get_s3_bucket_name", return_value="test-bucket"
            ),
            patch(
                "builtins.open", mock_open(read_data=sample_html_content)
            ) as mock_file,
            patch("aiohttp.ClientSession") as mock_aiohttp,
        ):
            # Mock HTTP error response
            mock_response = AsyncMock()
            mock_response.status = 404
            mock_response.read = AsyncMock(return_value=b"Not Found")

            # Create proper async context manager for the response
            class MockResponseContextManager:
                def __init__(self, response):
                    self.response = response

                async def __aenter__(self):
                    return self.response

                async def __aexit__(self, exc_type, exc_val, exc_tb):
                    return None

            # Mock the session
            mock_session = AsyncMock()
            mock_session.get = Mock(
                return_value=MockResponseContextManager(mock_response)
            )

            # Mock the ClientSession context manager
            class MockSessionContextManager:
                def __init__(self, session):
                    self.session = session

                async def __aenter__(self):
                    return self.session

                async def __aexit__(self, exc_type, exc_val, exc_tb):
                    return None

            mock_aiohttp.return_value = MockSessionContextManager(mock_session)

            result = await process_blog("test-blog", "https://example.com/test-blog")

            assert result["status"] == "failed"
            assert "error" in result
            assert "HTTP 404" in result["error"]

    @pytest.mark.asyncio
    async def test_process_notebook_success(
        self, mock_storage_manager, sample_notebook_content
    ):
        """Test successful notebook processing."""
        with (
            patch(
                "app.etl.tasks.ingestion.get_s3_bucket_name", return_value="test-bucket"
            ),
            patch(
                "app.etl.tasks.ingestion.get_storage_manager",
                return_value=mock_storage_manager,
            ),
            patch("app.etl.tasks.ingestion.update_tracking_index", return_value=True),
            patch(
                "builtins.open",
                mock_open(
                    read_data='{"cells": [], "metadata": {}, "nbformat": 4, "nbformat_minor": 0}'
                ),
            ) as mock_file,
            patch("aiohttp.ClientSession") as mock_aiohttp,
            patch("nbformat.reads") as mock_nbformat_reads,
            patch("nbconvert.MarkdownExporter") as mock_exporter_class,
        ):
            # Mock HTTP response
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.read = AsyncMock(
                return_value='{"cells": [], "metadata": {}, "nbformat": 4, "nbformat_minor": 0}'.encode()
            )

            # Create a proper async context manager
            class MockResponseContextManager:
                def __init__(self, response):
                    self.response = response

                async def __aenter__(self):
                    return self.response

                async def __aexit__(self, exc_type, exc_val, exc_tb):
                    return None

            # Mock the session
            mock_session = AsyncMock()
            mock_session.get = Mock(
                return_value=MockResponseContextManager(mock_response)
            )

            # Mock the ClientSession context manager
            class MockSessionContextManager:
                def __init__(self, session):
                    self.session = session

                async def __aenter__(self):
                    return self.session

                async def __aexit__(self, exc_type, exc_val, exc_tb):
                    return None

            mock_aiohttp.return_value = MockSessionContextManager(mock_session)

            # Mock nbformat
            mock_notebook = Mock()
            mock_nbformat_reads.return_value = mock_notebook

            # Mock MarkdownExporter
            mock_exporter = Mock()
            mock_exporter.from_notebook_node.return_value = (
                "# Test Notebook\n\nHello, World!",
                {},
            )
            mock_exporter_class.return_value = mock_exporter

            result = await process_notebook(
                "test-notebook", "https://github.com/user/repo/blob/main/notebook.ipynb"
            )

            assert result["status"] == "success"
            assert result["notebook_name"] == "test-notebook"
            assert "s3_url" in result
            assert "markdown_path" in result

    @pytest.mark.asyncio
    async def test_process_notebook_http_error(self):
        """Test notebook processing with HTTP error."""
        with (
            patch(
                "app.etl.tasks.ingestion.get_s3_bucket_name", return_value="test-bucket"
            ),
            patch("builtins.open", mock_open(read_data='{"cells": []}')) as mock_file,
            patch("aiohttp.ClientSession") as mock_aiohttp,
        ):
            # Mock HTTP error response
            mock_response = AsyncMock()
            mock_response.status = 404
            mock_response.read = AsyncMock(return_value=b"Not Found")

            # Create proper async context manager for the response
            class MockResponseContextManager:
                def __init__(self, response):
                    self.response = response

                async def __aenter__(self):
                    return self.response

                async def __aexit__(self, exc_type, exc_val, exc_tb):
                    return None

            # Mock the session
            mock_session = AsyncMock()
            mock_session.get = Mock(
                return_value=MockResponseContextManager(mock_response)
            )

            # Mock the ClientSession context manager
            class MockSessionContextManager:
                def __init__(self, session):
                    self.session = session

                async def __aenter__(self):
                    return self.session

                async def __aexit__(self, exc_type, exc_val, exc_tb):
                    return None

            mock_aiohttp.return_value = MockSessionContextManager(mock_session)

            result = await process_notebook(
                "test-notebook", "https://github.com/user/repo/blob/main/notebook.ipynb"
            )

            assert result["status"] == "failed"
            assert "error" in result
            assert "HTTP 404" in result["error"]

    @pytest.mark.asyncio
    async def test_process_repository_success(self, mock_storage_manager):
        """Test successful repository processing."""
        with (
            patch(
                "app.etl.tasks.ingestion.get_s3_bucket_name", return_value="test-bucket"
            ),
            patch(
                "app.etl.tasks.ingestion.get_storage_manager",
                return_value=mock_storage_manager,
            ),
            patch("app.etl.tasks.ingestion.update_tracking_index", return_value=True),
            patch("app.etl.tasks.ingestion.git.Repo") as mock_repo_class,
            patch("app.etl.tasks.ingestion.repo_to_pdf") as mock_repo_to_pdf,
        ):

            # Mock git repository
            mock_repo = Mock()
            mock_repo.remotes.origin.url = "https://github.com/user/repo.git"
            mock_repo_class.return_value = mock_repo

            # Mock repo_to_pdf function
            mock_repo_to_pdf.return_value = "test-repo.pdf"

            result = await process_repository(
                "test-repo", "https://github.com/user/test-repo"
            )

            assert result["status"] == "success"
            assert result["repo_name"] == "test-repo"
            assert "s3_url" in result
            assert "pdf_path" in result

    @pytest.mark.asyncio
    async def test_process_repository_git_error(self, mock_storage_manager):
        """Test repository processing with git error."""
        with (
            patch(
                "app.etl.tasks.ingestion.get_s3_bucket_name", return_value="test-bucket"
            ),
            patch(
                "app.etl.tasks.ingestion.get_storage_manager",
                return_value=mock_storage_manager,
            ),
            patch("app.etl.tasks.ingestion.git.Repo.clone_from") as mock_clone_from,
        ):

            # Mock git error
            mock_clone_from.side_effect = Exception("Git clone failed")

            result = await process_repository(
                "test-repo", "https://github.com/user/test-repo"
            )

            assert result["status"] == "failed"
            assert "error" in result
            assert "Git clone failed" in result["error"]

    @pytest.mark.asyncio
    async def test_process_blog_missing_dependencies(self, sample_html_content):
        """Test blog processing when required dependencies are missing."""
        with (
            patch(
                "app.etl.tasks.ingestion.get_s3_bucket_name", return_value="test-bucket"
            ),
            patch(
                "builtins.open", mock_open(read_data=sample_html_content)
            ) as mock_file,
            patch("aiohttp.ClientSession") as mock_aiohttp,
            patch(
                "bs4.BeautifulSoup", side_effect=ImportError("No module named 'bs4'")
            ),
        ):
            # Mock HTTP response
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.read = AsyncMock(return_value=b"<html>test</html>")

            # Create proper async context manager for the response
            class MockResponseContextManager:
                def __init__(self, response):
                    self.response = response

                async def __aenter__(self):
                    return self.response

                async def __aexit__(self, exc_type, exc_val, exc_tb):
                    return None

            # Mock the session
            mock_session = AsyncMock()
            mock_session.get = Mock(
                return_value=MockResponseContextManager(mock_response)
            )

            # Mock the ClientSession context manager
            class MockSessionContextManager:
                def __init__(self, session):
                    self.session = session

                async def __aenter__(self):
                    return self.session

                async def __aexit__(self, exc_type, exc_val, exc_tb):
                    return None

            mock_aiohttp.return_value = MockSessionContextManager(mock_session)

            result = await process_blog("test-blog", "https://example.com/test-blog")

            assert result["status"] == "failed"
            assert "error" in result
            assert "BeautifulSoup and markdownify are required" in result["error"]

    @pytest.mark.asyncio
    async def test_process_notebook_missing_dependencies(self):
        """Test notebook processing when required dependencies are missing."""
        with (
            patch(
                "app.etl.tasks.ingestion.get_s3_bucket_name", return_value="test-bucket"
            ),
            patch("builtins.open", mock_open(read_data='{"cells": []}')) as mock_file,
            patch("aiohttp.ClientSession") as mock_aiohttp,
            patch(
                "nbformat.reads", side_effect=ImportError("No module named 'nbformat'")
            ),
        ):
            # Mock HTTP response
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.read = AsyncMock(return_value=b'{"cells": []}')

            # Create proper async context manager for the response
            class MockResponseContextManager:
                def __init__(self, response):
                    self.response = response

                async def __aenter__(self):
                    return self.response

                async def __aexit__(self, exc_type, exc_val, exc_tb):
                    return None

            # Mock the session
            mock_session = AsyncMock()
            mock_session.get = Mock(
                return_value=MockResponseContextManager(mock_response)
            )

            # Mock the ClientSession context manager
            class MockSessionContextManager:
                def __init__(self, session):
                    self.session = session

                async def __aenter__(self):
                    return self.session

                async def __aexit__(self, exc_type, exc_val, exc_tb):
                    return None

            mock_aiohttp.return_value = MockSessionContextManager(mock_session)

            result = await process_notebook(
                "test-notebook", "https://github.com/user/repo/blob/main/notebook.ipynb"
            )

            assert result["status"] == "failed"
            assert "error" in result
            assert "nbformat and nbconvert are required" in result["error"]
