"""
Tests for ETL vectorization tasks.

This module tests the vectorization functionality including:
- PDF text extraction
- Markdown text extraction
- Text chunking
- Vector embedding generation
- RAG index storage
- Knowledge tracking updates
"""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.etl.tasks.vectorization import (
    chunk_text,
    extract_text_from_markdown,
    extract_text_from_pdf,
    get_latest_date_folder,
    list_content_files_in_folder,
    process_content_file,
    update_tracking_index_status,
    vectorize_and_store_chunks,
)
from app.utilities.s3_utils import get_s3_bucket_name


class TestVectorizationTasks:
    """Test cases for vectorization tasks."""

    @pytest.fixture
    def mock_vectorizer(self):
        """Mock text vectorizer."""
        vectorizer = Mock()
        vectorizer.embed.return_value = b"fake_vector_data"
        return vectorizer

    @pytest.fixture
    def mock_document_index(self):
        """Mock document index."""
        index = Mock()
        index.load = AsyncMock(return_value=None)
        return index

    @pytest.fixture
    def mock_redis_client(self):
        """Mock Redis client."""
        client = Mock()
        json_mock = Mock()
        json_mock.set = AsyncMock()
        client.json.return_value = json_mock
        return client

    @pytest.fixture
    def sample_text(self):
        """Sample text for testing."""
        return (
            "This is a sample text for testing vectorization. " * 50
        )  # Make it long enough to chunk

    def test_get_s3_bucket_name(self):
        """Test S3 bucket name generation."""
        with patch("app.utilities.s3_utils.get_env_var", return_value="test"):
            bucket_name = get_s3_bucket_name()
            assert bucket_name == "test-applied-ai-agent"

    @pytest.mark.asyncio
    async def test_get_latest_date_folder_success(self):
        """Test successful date folder retrieval."""
        mock_s3_client = Mock()
        mock_s3_client.list_objects_v2.return_value = {
            "CommonPrefixes": [
                {"Prefix": "processed/blog_text/2025-09-08/"},
                {"Prefix": "processed/blog_text/2025-09-09/"},
                {"Prefix": "processed/blog_text/2025-09-10/"},
            ]
        }

        with patch("boto3.client", return_value=mock_s3_client):
            result = await get_latest_date_folder("test-bucket", "blog")
            assert result == "2025-09-10"

    @pytest.mark.asyncio
    async def test_get_latest_date_folder_notebook(self):
        """Test date folder retrieval for notebooks."""
        mock_s3_client = Mock()
        mock_s3_client.list_objects_v2.return_value = {
            "CommonPrefixes": [
                {"Prefix": "processed/notebook_text/2025-09-08/"},
                {"Prefix": "processed/notebook_text/2025-09-09/"},
            ]
        }

        with patch("boto3.client", return_value=mock_s3_client):
            result = await get_latest_date_folder("test-bucket", "notebook")
            assert result == "2025-09-09"

    @pytest.mark.asyncio
    async def test_get_latest_date_folder_repo(self):
        """Test date folder retrieval for repositories."""
        mock_s3_client = Mock()
        mock_s3_client.list_objects_v2.return_value = {
            "CommonPrefixes": [
                {"Prefix": "processed/repo/2025-09-08/"},
            ]
        }

        with patch("boto3.client", return_value=mock_s3_client):
            result = await get_latest_date_folder("test-bucket", "repo")
            assert result == "2025-09-08"

    @pytest.mark.asyncio
    async def test_list_content_files_in_folder_blog(self):
        """Test listing blog markdown files."""
        mock_s3_client = Mock()
        mock_s3_client.list_objects_v2.return_value = {
            "Contents": [
                {"Key": "processed/blog_text/2025-09-08/test-blog.md"},
                {"Key": "processed/blog_text/2025-09-08/another-blog.md"},
            ]
        }

        with patch("boto3.client", return_value=mock_s3_client):
            result = await list_content_files_in_folder(
                "test-bucket", "blog", "2025-09-08"
            )

            assert len(result) == 2
            assert result[0]["filename"] == "test-blog.md"
            assert result[0]["content_type"] == "blog"
            assert result[0]["s3_key"] == "processed/blog_text/2025-09-08/test-blog.md"

    @pytest.mark.asyncio
    async def test_list_content_files_in_folder_notebook(self):
        """Test listing notebook markdown files."""
        mock_s3_client = Mock()
        mock_s3_client.list_objects_v2.return_value = {
            "Contents": [
                {"Key": "processed/notebook_text/2025-09-08/test-notebook.md"},
            ]
        }

        with patch("boto3.client", return_value=mock_s3_client):
            result = await list_content_files_in_folder(
                "test-bucket", "notebook", "2025-09-08"
            )

            assert len(result) == 1
            assert result[0]["filename"] == "test-notebook.md"
            assert result[0]["content_type"] == "notebook"
            assert (
                result[0]["s3_key"]
                == "processed/notebook_text/2025-09-08/test-notebook.md"
            )

    @pytest.mark.asyncio
    async def test_list_content_files_in_folder_repo(self):
        """Test listing repository PDF files."""
        mock_s3_client = Mock()
        mock_s3_client.list_objects_v2.return_value = {
            "Contents": [
                {"Key": "processed/repo/2025-09-08/test-repo.pdf"},
            ]
        }

        with patch("boto3.client", return_value=mock_s3_client):
            result = await list_content_files_in_folder(
                "test-bucket", "repo", "2025-09-08"
            )

            assert len(result) == 1
            assert result[0]["filename"] == "test-repo.pdf"
            assert result[0]["content_type"] == "repo"
            assert result[0]["s3_key"] == "processed/repo/2025-09-08/test-repo.pdf"

    @pytest.mark.asyncio
    async def test_extract_text_from_pdf(self, sample_text):
        """Test PDF text extraction."""
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp_file:
            temp_path = Path(temp_file.name)

            with patch("app.etl.tasks.vectorization.PyPDFLoader") as mock_loader_class:
                mock_loader = Mock()
                mock_doc = Mock()
                mock_doc.page_content = sample_text
                mock_loader.load.return_value = [mock_doc]
                mock_loader_class.return_value = mock_loader

                result = await extract_text_from_pdf(temp_path)
                assert result == sample_text

            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass  # File already deleted

    @pytest.mark.asyncio
    async def test_extract_text_from_markdown(self, sample_text):
        """Test markdown text extraction."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False
        ) as temp_file:
            temp_file.write(sample_text)
            temp_file.flush()
            temp_path = Path(temp_file.name)

            result = await extract_text_from_markdown(temp_path)
            assert result == sample_text

            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass  # File already deleted

    @pytest.mark.asyncio
    async def test_chunk_text(self, sample_text):
        """Test text chunking."""
        chunks = await chunk_text(sample_text, chunk_size=100, chunk_overlap=20)

        assert len(chunks) > 1  # Should create multiple chunks
        assert all(
            len(chunk) <= 100 for chunk in chunks
        )  # All chunks should be <= chunk_size
        assert all(
            isinstance(chunk, str) for chunk in chunks
        )  # All chunks should be strings

    @pytest.mark.asyncio
    async def test_vectorize_and_store_chunks_success(
        self, mock_vectorizer, mock_document_index, sample_text
    ):
        """Test successful vectorization and storage."""
        chunks = await chunk_text(sample_text, chunk_size=100, chunk_overlap=20)

        with (
            patch(
                "app.utilities.database.get_vectorizer", return_value=mock_vectorizer
            ),
            patch(
                "app.etl.tasks.vectorization.get_document_index",
                return_value=mock_document_index,
            ),
        ):

            result = await vectorize_and_store_chunks(
                chunks, "test-file.md", "blog", "2025-09-08"
            )

            assert result == len(chunks)
            mock_document_index.load.assert_called_once()

            # Check that the data was prepared correctly
            call_args = mock_document_index.load.call_args
            data = call_args[1]["data"]
            keys = call_args[1]["keys"]

            assert len(data) == len(chunks)
            assert len(keys) == len(chunks)

            # Check that each chunk has the required fields
            for i, chunk_data in enumerate(data):
                assert "name" in chunk_data
                assert "description" in chunk_data
                assert "source_file" in chunk_data
                assert "type" in chunk_data
                assert "vector" in chunk_data
                assert "chunk_index" in chunk_data
                assert "source_date" in chunk_data
                assert "update_date" in chunk_data
                assert "updated_at" in chunk_data

    @pytest.mark.asyncio
    async def test_vectorize_and_store_chunks_empty(
        self, mock_vectorizer, mock_document_index
    ):
        """Test vectorization with empty chunks."""
        with (
            patch(
                "app.utilities.database.get_vectorizer", return_value=mock_vectorizer
            ),
            patch(
                "app.etl.tasks.vectorization.get_document_index",
                return_value=mock_document_index,
            ),
        ):

            result = await vectorize_and_store_chunks(
                [], "test-file.md", "blog", "2025-09-08"
            )

            assert result == 0
            mock_document_index.load.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_tracking_index_success(self, mock_redis_client):
        """Test successful tracking index update."""
        # Mock existing record
        existing_record = {
            "name": "test-content",
            "content_type": "blog",
            "processing_status": "ingested",
            "retry_count": 0,
        }
        mock_redis_client.json.return_value.get = AsyncMock(
            return_value=existing_record
        )
        mock_redis_client.json.return_value.set = AsyncMock()

        with patch(
            "app.utilities.database.get_redis_client", return_value=mock_redis_client
        ):
            result = await update_tracking_index_status("test-content", "vectorized")

            assert result is True
            mock_redis_client.json.return_value.get.assert_called_once_with(
                "knowledge_tracking:test-content"
            )
            mock_redis_client.json.return_value.set.assert_called_once()

            # Check the call arguments
            call_args = mock_redis_client.json.return_value.set.call_args
            assert call_args[0][0] == "knowledge_tracking:test-content"
            assert call_args[0][1] == "$"

            updated_record = call_args[0][2]
            assert updated_record["name"] == "test-content"
            assert updated_record["content_type"] == "blog"
            assert updated_record["processing_status"] == "vectorized"

    @pytest.mark.asyncio
    async def test_update_tracking_index_failure(self, mock_redis_client):
        """Test tracking index update failure."""
        # Mock existing record
        existing_record = {
            "name": "test-content",
            "content_type": "blog",
            "processing_status": "ingested",
            "retry_count": 0,
        }
        mock_redis_client.json.return_value.get = AsyncMock(
            return_value=existing_record
        )
        mock_redis_client.json.return_value.set = AsyncMock(
            side_effect=Exception("Redis error")
        )

        with patch(
            "app.utilities.database.get_redis_client", return_value=mock_redis_client
        ):
            result = await update_tracking_index_status("test-content", "vectorized")

            assert result is False

    @pytest.mark.asyncio
    async def test_process_content_file_markdown_success(
        self, mock_vectorizer, mock_document_index, sample_text
    ):
        """Test successful markdown file processing."""
        file_info = {
            "s3_key": "processed/blog_text/2025-09-08/test-blog.md",
            "filename": "test-blog.md",
            "content_type": "blog",
            "date_folder": "2025-09-08",
        }

        with (
            patch(
                "app.utilities.database.get_vectorizer", return_value=mock_vectorizer
            ),
            patch(
                "app.etl.tasks.vectorization.get_document_index",
                return_value=mock_document_index,
            ),
            patch("app.etl.tasks.vectorization.download_file_from_s3") as mock_download,
            patch(
                "app.etl.tasks.vectorization.extract_text_from_markdown",
                return_value=sample_text,
            ),
            patch("app.etl.tasks.vectorization.chunk_text", return_value=[sample_text]),
            patch(
                "app.etl.tasks.vectorization.update_tracking_index_status",
                return_value=True,
            ),
            patch("boto3.client") as mock_boto,
        ):

            # Mock S3 download
            with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as temp_file:
                temp_path = Path(temp_file.name)
                mock_download.return_value = temp_path

                result = await process_content_file("test-bucket", file_info)

                assert result["status"] == "success"
                assert result["filename"] == "test-blog.md"
                assert result["content_type"] == "blog"
                assert result["chunk_count"] == 1
                assert result["tracking_updated"] is True

                try:
                    temp_path.unlink()
                except FileNotFoundError:
                    pass  # File already deleted

    @pytest.mark.asyncio
    async def test_process_content_file_pdf_success(
        self, mock_vectorizer, mock_document_index, sample_text
    ):
        """Test successful PDF file processing."""
        file_info = {
            "s3_key": "processed/repo/2025-09-08/test-repo.pdf",
            "filename": "test-repo.pdf",
            "content_type": "repo",
            "date_folder": "2025-09-08",
        }

        with (
            patch(
                "app.utilities.database.get_vectorizer", return_value=mock_vectorizer
            ),
            patch(
                "app.etl.tasks.vectorization.get_document_index",
                return_value=mock_document_index,
            ),
            patch("app.etl.tasks.vectorization.download_file_from_s3") as mock_download,
            patch(
                "app.etl.tasks.vectorization.extract_text_from_pdf",
                return_value=sample_text,
            ),
            patch("app.etl.tasks.vectorization.chunk_text", return_value=[sample_text]),
            patch(
                "app.etl.tasks.vectorization.update_tracking_index_status",
                return_value=True,
            ),
            patch("boto3.client") as mock_boto,
        ):

            # Mock S3 download
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp_file:
                temp_path = Path(temp_file.name)
                mock_download.return_value = temp_path

                result = await process_content_file("test-bucket", file_info)

                assert result["status"] == "success"
                assert result["filename"] == "test-repo.pdf"
                assert result["content_type"] == "repo"
                assert result["chunk_count"] == 1
                assert result["tracking_updated"] is True

                try:
                    temp_path.unlink()
                except FileNotFoundError:
                    pass  # File already deleted

    @pytest.mark.asyncio
    async def test_process_content_file_unsupported_type(self):
        """Test processing unsupported file type."""
        file_info = {
            "s3_key": "processed/test/2025-09-08/test.txt",
            "filename": "test.txt",
            "content_type": "test",
            "date_folder": "2025-09-08",
        }

        with (
            patch("app.etl.tasks.vectorization.download_file_from_s3") as mock_download,
            patch("boto3.client") as mock_boto,
        ):

            # Mock S3 download
            with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as temp_file:
                temp_path = Path(temp_file.name)
                mock_download.return_value = temp_path

                result = await process_content_file("test-bucket", file_info)

                assert result["status"] == "failed"
                assert "Unsupported file type" in result["error"]

                try:
                    temp_path.unlink()
                except FileNotFoundError:
                    pass  # File already deleted

    @pytest.mark.asyncio
    async def test_process_content_file_no_chunks(
        self, mock_vectorizer, mock_document_index
    ):
        """Test processing file that produces no chunks."""
        file_info = {
            "s3_key": "processed/blog_text/2025-09-08/empty-blog.md",
            "filename": "empty-blog.md",
            "content_type": "blog",
            "date_folder": "2025-09-08",
        }

        with (
            patch(
                "app.utilities.database.get_vectorizer", return_value=mock_vectorizer
            ),
            patch(
                "app.etl.tasks.vectorization.get_document_index",
                return_value=mock_document_index,
            ),
            patch("app.etl.tasks.vectorization.download_file_from_s3") as mock_download,
            patch(
                "app.etl.tasks.vectorization.extract_text_from_markdown",
                return_value="",
            ),
            patch("app.etl.tasks.vectorization.chunk_text", return_value=[]),
            patch("boto3.client") as mock_boto,
        ):

            # Mock S3 download
            with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as temp_file:
                temp_path = Path(temp_file.name)
                mock_download.return_value = temp_path

                result = await process_content_file("test-bucket", file_info)

                assert result["status"] == "failed"
                assert result["chunk_count"] == 0
                assert result["tracking_updated"] is False

                try:
                    temp_path.unlink()
                except FileNotFoundError:
                    pass  # File already deleted
