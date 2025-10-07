"""
Tests for content management API endpoints.

This module tests the content router functionality including:
- Ingestion pipeline endpoints
- Vectorization pipeline endpoints
- Error handling
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.api.routers.content import (
    get_redis_url,
    run_async_ingestion_pipeline,
    run_async_vectorization_pipeline,
)


class TestContentRouter:
    """Test cases for content router endpoints."""

    def test_get_redis_url(self):
        """Test Redis URL retrieval."""
        with patch(
            "app.api.routers.content.get_env_var", return_value="redis://test:6379/0"
        ):
            url = get_redis_url()
            assert url == "redis://test:6379/0"

    def test_get_redis_url_default(self):
        """Test Redis URL with default value."""
        with patch(
            "app.api.routers.content.get_env_var",
            side_effect=lambda key, default: default,
        ):
            url = get_redis_url()
            assert url == "redis://localhost:6379/0"

    @pytest.mark.asyncio
    async def test_run_async_ingestion_pipeline_success(self):
        """Test successful async ingestion pipeline."""
        # Mock the ingestion query function to return sample content
        mock_content = [
            {
                "name": "test-blog",
                "content_type": "blog",
                "content_url": "https://example.com/blog",
            },
            {
                "name": "test-notebook",
                "content_type": "notebook",
                "content_url": "https://github.com/user/repo/notebook.ipynb",
            },
        ]

        # Mock the Docket task queue
        mock_docket = AsyncMock()
        mock_docket.__aenter__ = AsyncMock(return_value=mock_docket)
        mock_docket.__aexit__ = AsyncMock(return_value=None)

        # Track calls to docket.add for verification
        add_calls = []

        def mock_add(func, **kwargs):
            add_calls.append({"func": func, "kwargs": kwargs})
            print(f"docket.add called with {func.__name__}")

            async def task_callable(*args, **task_kwargs):
                return None

            return task_callable

        mock_docket.add = mock_add

        # Track context manager calls
        enter_called = False
        exit_called = False

        async def mock_enter(self):
            nonlocal enter_called
            enter_called = True
            print("Docket context manager entered")
            return mock_docket

        async def mock_exit(self, exc_type, exc_val, exc_tb):
            nonlocal exit_called
            exit_called = True
            print("Docket context manager exited")
            return None

        mock_docket.__aenter__ = mock_enter
        mock_docket.__aexit__ = mock_exit

        with (
            patch(
                "app.api.routers.content.query_content_for_ingestion",
                return_value=mock_content,
            ) as mock_query,
            patch("app.api.routers.content.Docket", return_value=mock_docket),
            patch("app.api.routers.content.filter_content_by_type") as mock_filter,
            patch("app.api.routers.content.logger") as mock_logger,
        ):
            # Mock the filter function to return the expected content
            def filter_side_effect(content, content_type):
                filtered = [
                    item for item in content if item["content_type"] == content_type
                ]
                print(
                    f"Filtering {content_type}: {len(filtered)} items from {len(content)} total"
                )
                return filtered

            mock_filter.side_effect = filter_side_effect
            print(f"Mock content: {mock_content}")

            # Capture logger calls to see what's happening
            logger_calls = []

            def log_side_effect(*args, **kwargs):
                logger_calls.append(args[0] if args else "")
                print(f"LOG: {args[0] if args else ''}")

            mock_logger.info.side_effect = log_side_effect

            try:
                result = await run_async_ingestion_pipeline()
            except Exception as e:
                print(f"Exception occurred: {e}")
                import traceback

                traceback.print_exc()
                raise

            assert result["status"] == "success"
            assert "ingestion_date" in result
            assert result["total_tasks_queued"] == 2
            assert len(result["blogs"]) == 1
            assert len(result["notebooks"]) == 1
            assert len(result["repos"]) == 0

    @pytest.mark.asyncio
    async def test_run_async_ingestion_pipeline_empty_content(self):
        """Test ingestion pipeline with no content to process."""
        mock_docket = AsyncMock()
        mock_docket.__aenter__ = AsyncMock(return_value=mock_docket)
        mock_docket.__aexit__ = AsyncMock(return_value=None)

        # Mock docket.add to return a callable that can be awaited
        def mock_add(func, **kwargs):
            async def task_callable(*args, **task_kwargs):
                return None

            return task_callable

        mock_docket.add = mock_add

        with (
            patch(
                "app.api.routers.content.query_content_for_ingestion", return_value=[]
            ),
            patch("app.api.routers.content.Docket", return_value=mock_docket),
        ):
            result = await run_async_ingestion_pipeline()

            assert result["status"] == "success"
            assert result["total_tasks_queued"] == 0
            assert len(result["blogs"]) == 0
            assert len(result["notebooks"]) == 0
            assert len(result["repos"]) == 0

    @pytest.mark.asyncio
    async def test_run_async_ingestion_pipeline_error(self):
        """Test ingestion pipeline with error."""
        with patch(
            "app.api.routers.content.query_content_for_ingestion",
            side_effect=Exception("Query error"),
        ):
            with pytest.raises(Exception, match="Query error"):
                await run_async_ingestion_pipeline()

    @pytest.mark.asyncio
    async def test_run_async_vectorization_pipeline_success(self):
        """Test successful async vectorization pipeline."""
        # Mock content ready for vectorization
        mock_content_files = [
            {
                "s3_key": "processed/blog_text/2025-09-08/test-blog.md",
                "filename": "test-blog.md",
                "content_type": "blog",
                "date_folder": "2025-09-08",
            }
        ]

        mock_docket = AsyncMock()
        mock_docket.__aenter__ = AsyncMock(return_value=mock_docket)
        mock_docket.__aexit__ = AsyncMock(return_value=None)

        # Mock docket.add to return a callable that can be awaited
        def mock_add(func, **kwargs):
            async def task_callable(*args, **task_kwargs):
                return None

            return task_callable

        mock_docket.add = mock_add

        with (
            patch(
                "app.api.routers.content.get_content_ready_for_vectorization",
                return_value=mock_content_files,
            ),
            patch(
                "app.utilities.s3_utils.get_s3_bucket_name", return_value="test-bucket"
            ),
            patch("app.api.routers.content.Docket", return_value=mock_docket),
        ):
            result = await run_async_vectorization_pipeline()

            assert result["status"] == "success"
            assert "vectorization_date" in result
            assert result["total_tasks_queued"] == 1
            assert result["content_items_queued"] == 1
            assert len(result["details"]) == 1

    @pytest.mark.asyncio
    async def test_run_async_vectorization_pipeline_no_files(self):
        """Test vectorization pipeline with no files found."""
        mock_docket = AsyncMock()
        mock_docket.__aenter__ = AsyncMock(return_value=mock_docket)
        mock_docket.__aexit__ = AsyncMock(return_value=None)

        # Mock docket.add to return a callable that can be awaited
        def mock_add(func, **kwargs):
            async def task_callable(*args, **task_kwargs):
                return None

            return task_callable

        mock_docket.add = mock_add

        with (
            patch(
                "app.api.routers.content.get_content_ready_for_vectorization",
                return_value=[],
            ),
            patch("app.api.routers.content.Docket", return_value=mock_docket),
        ):
            result = await run_async_vectorization_pipeline()

            assert result["status"] == "success"
            assert result["total_tasks_queued"] == 0
            assert result["content_items_queued"] == 0
            assert len(result["details"]) == 0

    @pytest.mark.asyncio
    async def test_run_async_vectorization_pipeline_error(self):
        """Test vectorization pipeline with error."""
        with patch(
            "app.api.routers.content.get_content_ready_for_vectorization",
            side_effect=Exception("Vectorization error"),
        ):
            with pytest.raises(Exception, match="Vectorization error"):
                await run_async_vectorization_pipeline()

    @pytest.mark.asyncio
    async def test_ingestion_pipeline_task_queuing(self):
        """Test that ingestion tasks are properly queued with Docket."""
        mock_content = [
            {
                "name": "test-blog",
                "content_type": "blog",
                "content_url": "https://example.com/blog",
            },
        ]

        mock_docket = AsyncMock()
        mock_docket.__aenter__ = AsyncMock(return_value=mock_docket)
        mock_docket.__aexit__ = AsyncMock(return_value=None)

        # Track calls to docket.add for verification
        add_calls = []

        def mock_add(func, **kwargs):
            add_calls.append({"func": func, "kwargs": kwargs})

            async def task_callable(*args, **task_kwargs):
                return None

            return task_callable

        mock_docket.add = mock_add

        with (
            patch(
                "app.api.routers.content.query_content_for_ingestion",
                return_value=mock_content,
            ),
            patch("app.api.routers.content.Docket", return_value=mock_docket),
        ):

            await run_async_ingestion_pipeline()

            # Verify that docket.add was called for the blog
            assert len(add_calls) == 1
            assert add_calls[0]["func"].__name__ == "process_blog"

    @pytest.mark.asyncio
    async def test_vectorization_pipeline_task_queuing(self):
        """Test that vectorization tasks are properly queued with Docket."""
        mock_content_files = [
            {
                "s3_key": "processed/blog_text/2025-09-08/test-blog.md",
                "filename": "test-blog.md",
                "content_type": "blog",
                "date_folder": "2025-09-08",
            }
        ]

        mock_docket = AsyncMock()
        mock_docket.__aenter__ = AsyncMock(return_value=mock_docket)
        mock_docket.__aexit__ = AsyncMock(return_value=None)

        # Track calls to docket.add for verification
        add_calls = []

        def mock_add(func, **kwargs):
            add_calls.append({"func": func, "kwargs": kwargs})

            async def task_callable(*args, **task_kwargs):
                return None

            return task_callable

        mock_docket.add = mock_add

        with (
            patch(
                "app.api.routers.content.get_content_ready_for_vectorization",
                return_value=mock_content_files,
            ),
            patch(
                "app.utilities.s3_utils.get_s3_bucket_name", return_value="test-bucket"
            ),
            patch("app.api.routers.content.Docket", return_value=mock_docket),
        ):
            await run_async_vectorization_pipeline()

            # Verify that docket.add was called for the content file
            assert len(add_calls) == 1
            assert add_calls[0]["func"].__name__ == "process_content_file"

    @pytest.mark.asyncio
    async def test_ingestion_pipeline_result_structure(self):
        """Test that ingestion pipeline returns correct result structure."""
        mock_content = [
            {
                "name": "test-blog",
                "content_type": "blog",
                "content_url": "https://example.com/blog",
            },
        ]

        mock_docket = AsyncMock()
        mock_docket.__aenter__ = AsyncMock(return_value=mock_docket)
        mock_docket.__aexit__ = AsyncMock(return_value=None)

        # Mock docket.add to return a callable that can be awaited
        def mock_add(func, **kwargs):
            async def task_callable(*args, **task_kwargs):
                return None

            return task_callable

        mock_docket.add = mock_add

        with (
            patch(
                "app.api.routers.content.query_content_for_ingestion",
                return_value=mock_content,
            ),
            patch("app.api.routers.content.Docket", return_value=mock_docket),
        ):

            result = await run_async_ingestion_pipeline()

            # Check required fields
            required_fields = [
                "status",
                "ingestion_date",
                "repos",
                "blogs",
                "notebooks",
                "total_tasks_queued",
            ]
            for field in required_fields:
                assert field in result

            # Check data types
            assert isinstance(result["status"], str)
            assert isinstance(result["ingestion_date"], str)
            assert isinstance(result["repos"], list)
            assert isinstance(result["blogs"], list)
            assert isinstance(result["notebooks"], list)
            assert isinstance(result["total_tasks_queued"], int)

    @pytest.mark.asyncio
    async def test_vectorization_pipeline_result_structure(self):
        """Test that vectorization pipeline returns correct result structure."""
        mock_content_files = [
            {
                "s3_key": "processed/blog_text/2025-09-08/test-blog.md",
                "filename": "test-blog.md",
                "content_type": "blog",
                "date_folder": "2025-09-08",
            }
        ]

        mock_docket = AsyncMock()
        mock_docket.__aenter__ = AsyncMock(return_value=mock_docket)
        mock_docket.__aexit__ = AsyncMock(return_value=None)

        # Mock docket.add to return a callable that can be awaited
        def mock_add(func, **kwargs):
            async def task_callable(*args, **task_kwargs):
                return None

            return task_callable

        mock_docket.add = mock_add

        with (
            patch(
                "app.api.routers.content.get_content_ready_for_vectorization",
                return_value=mock_content_files,
            ),
            patch(
                "app.utilities.s3_utils.get_s3_bucket_name", return_value="test-bucket"
            ),
            patch("app.api.routers.content.Docket", return_value=mock_docket),
        ):
            result = await run_async_vectorization_pipeline()

            # Check required fields for the actual vectorization pipeline response
            required_fields = [
                "status",
                "vectorization_date",
                "content_items_queued",
                "total_tasks_queued",
                "details",
            ]
            for field in required_fields:
                assert field in result

            # Check data types
            assert isinstance(result["status"], str)
            assert isinstance(result["vectorization_date"], str)
            assert isinstance(result["content_items_queued"], int)
            assert isinstance(result["total_tasks_queued"], int)
            assert isinstance(result["details"], list)

    @pytest.mark.asyncio
    async def test_ingestion_pipeline_task_keys(self):
        """Test that ingestion pipeline generates correct task keys."""
        mock_content = [
            {
                "name": "test-blog",
                "content_type": "blog",
                "content_url": "https://example.com/blog",
            },
            {
                "name": "test-notebook",
                "content_type": "notebook",
                "content_url": "https://github.com/user/repo/notebook.ipynb",
            },
        ]

        mock_docket = AsyncMock()
        mock_docket.__aenter__ = AsyncMock(return_value=mock_docket)
        mock_docket.__aexit__ = AsyncMock(return_value=None)

        # Mock docket.add to return a callable that can be awaited
        def mock_add(func, **kwargs):
            async def task_callable(*args, **task_kwargs):
                return None

            return task_callable

        mock_docket.add = mock_add

        with (
            patch(
                "app.api.routers.content.query_content_for_ingestion",
                return_value=mock_content,
            ),
            patch("app.api.routers.content.Docket", return_value=mock_docket),
        ):

            result = await run_async_ingestion_pipeline()

            # Check that task keys are included in results
            for blog in result["blogs"]:
                assert "task_key" in blog
                assert blog["task_key"].startswith("blog_")

            for notebook in result["notebooks"]:
                assert "task_key" in notebook
                assert notebook["task_key"].startswith("notebook_")
