"""
Clean Glean search service that fixes the enum validation issue with a simple patch.
"""

import asyncio
import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam

load_dotenv()
logger = logging.getLogger(__name__)

# Apply the enum fix patch once at module level
_patch_applied = False


def _apply_enum_fix_patch():
    """Apply the enum case fix patch to the Glean SDK."""
    global _patch_applied
    if _patch_applied:
        return

    try:
        from glean.api_client.utils import serializers

        # Store original function
        _original_unmarshal_json = serializers.unmarshal_json

        def _fix_enum_case_issues(data):
            """Fix known enum case sensitivity issues."""
            if isinstance(data, dict):
                fixed_data = {}
                for key, value in data.items():
                    if key == "relation" and isinstance(value, str):
                        # Fix the known lowercase enum issues
                        enum_fixes = {
                            "contact": "CONTACT",
                            "attachment": "ATTACHMENT",
                            "canonical": "CANONICAL",
                            "case": "CASE",
                            "conversation_messages": "CONVERSATION_MESSAGES",
                            "expert": "EXPERT",
                            "from": "FROM",
                            "highlight": "HIGHLIGHT",
                            "opportunity": "OPPORTUNITY",
                            "recent": "RECENT",
                            "source": "SOURCE",
                            "ticket": "TICKET",
                            "transcript": "TRANSCRIPT",
                            "with": "WITH",
                        }
                        fixed_value = enum_fixes.get(value.lower(), value.upper())
                        fixed_data[key] = fixed_value
                        logger.debug(f"Fixed enum: {value} -> {fixed_value}")
                    else:
                        fixed_data[key] = _fix_enum_case_issues(value)
                return fixed_data
            elif isinstance(data, list):
                return [_fix_enum_case_issues(item) for item in data]
            else:
                return data

        def patched_unmarshal_json(raw_json, typ):
            """Patched version that fixes enum case issues before validation."""
            try:
                # Try original first
                return _original_unmarshal_json(raw_json, typ)
            except Exception as e:
                if "validation error" in str(e).lower() and "relation" in str(e):
                    logger.debug("Fixing enum case issues and retrying...")
                    # Fix the JSON and retry
                    data = json.loads(raw_json)
                    fixed_data = _fix_enum_case_issues(data)
                    fixed_json = json.dumps(fixed_data)
                    return _original_unmarshal_json(fixed_json, typ)
                else:
                    raise

        # Apply the patch
        serializers.unmarshal_json = patched_unmarshal_json
        _patch_applied = True
        logger.info("Applied Glean SDK enum fix patch")

    except ImportError:
        logger.warning("Glean SDK not available, enum fix patch not applied")
    except Exception as e:
        logger.error(f"Failed to apply enum fix patch: {e}")


# Apply patch when module is imported
_apply_enum_fix_patch()


class GleanSearchService:
    """Simple, clean Glean search service with enum validation fix."""

    def __init__(self):
        self.api_token = os.getenv("GLEAN_API_TOKEN")
        self.instance = os.getenv("GLEAN_INSTANCE")
        self._executor = ThreadPoolExecutor(max_workers=4)
        self._last_request_time = 0
        self._min_request_interval = 1.0  # Minimum 1 second between requests

        if not self.api_token:
            logger.warning("GLEAN_API_TOKEN not found in environment variables")
        if not self.instance:
            logger.warning("GLEAN_INSTANCE not found in environment variables")

    def _rate_limit_check(self):
        """Ensure we don't make requests too frequently."""
        current_time = time.time()
        time_since_last = current_time - self._last_request_time

        if time_since_last < self._min_request_interval:
            sleep_time = self._min_request_interval - time_since_last
            logger.info(f"Rate limiting: waiting {sleep_time:.1f}s before next request")
            time.sleep(sleep_time)

        self._last_request_time = time.time()

    def _get_client(self):
        """Get a Glean client instance."""
        if not self.api_token or not self.instance:
            raise ValueError("Missing GLEAN_API_TOKEN or GLEAN_INSTANCE")

        try:
            from glean.api_client import Glean

            return Glean(api_token=self.api_token, instance=self.instance)
        except ImportError:
            raise ImportError(
                "glean-api-client package required. Install with: pip install glean-api-client"
            )

    async def search(
        self,
        query: str,
        max_results: int = 10,
        datasources: Optional[List[str]] = None,
        filters: Optional[Dict[str, Any]] = None,
        timeout_millis: int = 30000,
    ) -> Dict[str, Any]:
        """
        Perform search using Glean API.

        Args:
            query: Search query
            max_results: Maximum number of results to return
            datasources: List of datasource names to restrict search to
            filters: Additional filters to apply to search
            timeout_millis: Request timeout in milliseconds

        Returns:
            Dictionary containing search results
        """
        if not self.api_token or not self.instance:
            return {
                "error": "Glean API token or instance not configured",
                "results": [],
                "summary": "Glean search is not available - missing API key or instance",
            }

        try:
            from glean.api_client import models

            # Build request options if filters specified
            request_options = None
            if datasources or filters:
                facet_filters = []

                # Add datasource filter
                if datasources:
                    facet_filters.append(
                        models.FacetFilter(
                            field_name="datasource",
                            values=[
                                models.FacetFilterValue(
                                    value=ds,
                                    relation_type=models.RelationType.EQUALS,
                                )
                                for ds in datasources
                            ],
                        )
                    )

                # Add custom filters
                if filters:
                    for field_name, field_values in filters.items():
                        if isinstance(field_values, list):
                            facet_filters.append(
                                models.FacetFilter(
                                    field_name=field_name,
                                    values=[
                                        models.FacetFilterValue(
                                            value=str(val),
                                            relation_type=models.RelationType.EQUALS,
                                        )
                                        for val in field_values
                                    ],
                                )
                            )

                if facet_filters:
                    request_options = models.SearchRequestOptions(
                        facet_filters=facet_filters,
                        facet_bucket_size=1000,
                    )

            # Execute search in thread pool
            loop = asyncio.get_event_loop()

            def _search():
                with self._get_client() as client:
                    return client.client.search.query(
                        query=query,
                        page_size=max_results,
                        request_options=request_options,
                        timeout_millis=timeout_millis,
                    )

            response = await loop.run_in_executor(self._executor, _search)
            return self._format_results(response, query)

        except Exception as e:
            logger.error(f"Glean search error: {e}")
            return {
                "error": str(e),
                "results": [],
            }

    async def chat_search(
        self,
        query: str,
        timeout_millis: int = 30000,
    ) -> Dict[str, Any]:
        """
        Perform conversational search using Glean's chat API.

        Args:
            query: Natural language query
            timeout_millis: Request timeout in milliseconds

        Returns:
            Dictionary containing chat response
        """
        if not self.api_token or not self.instance:
            return {
                "error": "Glean API token or instance not configured",
                "response": "Glean chat search is not available - missing API key or instance",
            }

        try:
            from glean.api_client import models

            # Prepare chat message
            messages = [
                models.ChatMessage(fragments=[models.ChatMessageFragment(text=query)])
            ]

            # Execute chat in thread pool
            loop = asyncio.get_event_loop()

            def _chat():
                with self._get_client() as client:
                    return client.client.chat.create(
                        messages=messages, timeout_millis=timeout_millis
                    )

            response = await loop.run_in_executor(self._executor, _chat)
            return self._format_chat_results(response, query)

        except Exception as e:
            logger.error(f"Glean chat error: {e}")
            return {
                "error": str(e),
                "response": "",
            }

    def _format_results(self, response, query: str) -> Dict[str, Any]:
        """Format search response into clean structure."""
        try:
            # Handle string responses (error case)
            if isinstance(response, str):
                return {
                    "query": query,
                    "results": [],
                    "total_results": 0,
                    "error": f"Received unexpected string response: {response}",
                }

            # Handle None responses
            if response is None:
                return {
                    "query": query,
                    "results": [],
                    "total_results": 0,
                    "error": "Received None response",
                }

            results = []

            # Handle both SDK response objects and raw response objects
            if isinstance(response, dict):
                # Already parsed dict responses
                api_results = response.get("results", [])
            elif hasattr(response, "results"):
                # Standard SDK response
                api_results = getattr(response, "results", []) or []
            else:
                # Try to access results directly
                api_results = getattr(response, "results", []) or []

            for result in api_results:
                # Extract snippet content - handle both dict and object results
                snippet_content = ""
                if isinstance(result, dict):
                    # Raw dict response
                    snippets = result.get("snippets", [])
                    if snippets and len(snippets) > 0:
                        snippet_obj = snippets[0]
                        if isinstance(snippet_obj, dict):
                            snippet_content = snippet_obj.get(
                                "snippet", ""
                            ) or snippet_obj.get("text", "")
                        else:
                            snippet_content = getattr(
                                snippet_obj, "snippet", ""
                            ) or getattr(snippet_obj, "text", "")
                else:
                    # SDK object response
                    snippets = getattr(result, "snippets", [])
                    if snippets:
                        snippet_content = getattr(snippets[0], "text", "") or getattr(
                            snippets[0], "snippet", ""
                        )

                # Extract metadata and other fields - handle both dict and object types
                if isinstance(result, dict):
                    # Raw dict response
                    title = result.get("title", "")
                    url = result.get("url", "")
                    score = result.get("score", 0.0)

                    metadata = result.get("metadata", {})
                    if isinstance(metadata, dict):
                        datasource_obj = metadata.get("datasource", "")
                        if isinstance(datasource_obj, dict):
                            datasource = datasource_obj.get("name", "")
                        else:
                            datasource = str(datasource_obj) if datasource_obj else ""
                        document_type = metadata.get("objectType", "")
                        created_at = metadata.get("createTime", "")
                        updated_at = metadata.get("updateTime", "")
                    else:
                        datasource = (
                            getattr(metadata, "datasource", "")
                            if hasattr(metadata, "datasource")
                            else ""
                        )
                        document_type = (
                            getattr(metadata, "objectType", "")
                            if hasattr(metadata, "objectType")
                            else ""
                        )
                        created_at = (
                            getattr(metadata, "createTime", "")
                            if hasattr(metadata, "createTime")
                            else ""
                        )
                        updated_at = (
                            getattr(metadata, "updateTime", "")
                            if hasattr(metadata, "updateTime")
                            else ""
                        )
                else:
                    # SDK object response
                    title = getattr(result, "title", "")
                    url = getattr(result, "url", "")
                    score = getattr(result, "score", 0.0)

                    metadata = getattr(result, "metadata", {})
                    if hasattr(metadata, "__dict__"):
                        # It's an object, use attribute access
                        datasource = getattr(metadata, "datasource", "")
                        document_type = getattr(metadata, "objectType", "")
                        created_at = getattr(metadata, "createTime", "")
                        updated_at = getattr(metadata, "updateTime", "")
                    else:
                        # It's already a dict
                        datasource = metadata.get("datasource", "") if metadata else ""
                        document_type = (
                            metadata.get("objectType", "") if metadata else ""
                        )
                        created_at = metadata.get("createTime", "") if metadata else ""
                        updated_at = metadata.get("updateTime", "") if metadata else ""

                results.append(
                    {
                        "title": title,
                        "url": url,
                        "content": snippet_content,
                        "score": score,
                        "datasource": datasource,
                        "document_type": document_type,
                        "created_at": created_at,
                        "updated_at": updated_at,
                    }
                )

            # Extract tracking token - handle both response types
            tracking_token = ""
            if isinstance(response, dict):
                tracking_token = response.get("tracking_token", "") or response.get(
                    "trackingToken", ""
                )
            else:
                tracking_token = getattr(response, "tracking_token", "") or getattr(
                    response, "trackingToken", ""
                )

            return {
                "query": query,
                "results": results,
                "total_results": len(results),
                "tracking_token": tracking_token,
            }

        except Exception as e:
            logger.error(f"Error formatting results: {e}")
            return {
                "query": query,
                "results": [],
                "total_results": 0,
                "error": f"Error formatting results: {str(e)}",
            }

    def _format_chat_results(self, response, query: str) -> Dict[str, Any]:
        """Format chat response into clean structure."""
        try:
            response_text = ""
            citations = []

            # Handle dictionary responses first
            if isinstance(response, dict):
                messages = response.get("messages", [])
                if messages:
                    latest_message = (
                        messages[-1] if isinstance(messages, list) else messages
                    )
                    fragments = (
                        latest_message.get("fragments", [])
                        if isinstance(latest_message, dict)
                        else []
                    )
                    if isinstance(fragments, list):
                        for fragment in fragments:
                            if isinstance(fragment, dict) and fragment.get("text"):
                                response_text += fragment["text"]

                citations_data = response.get("citations", [])
                if isinstance(citations_data, list):
                    for citation in citations_data:
                        if isinstance(citation, dict):
                            datasource = ""
                            if "datasource" in citation:
                                ds = citation["datasource"]
                                if isinstance(ds, dict):
                                    datasource = ds.get("name", "")
                                else:
                                    datasource = str(ds)

                            citations.append(
                                {
                                    "title": citation.get("title", ""),
                                    "url": citation.get("url", ""),
                                    "snippet": citation.get("snippet", ""),
                                    "datasource": datasource,
                                }
                            )
            else:
                # Handle SDK object responses
                if hasattr(response, "messages") and response.messages:
                    latest_message = response.messages[-1]
                    if hasattr(latest_message, "fragments"):
                        for fragment in latest_message.fragments:
                            if hasattr(fragment, "text") and fragment.text:
                                response_text += fragment.text

                # Extract citations
                if hasattr(response, "citations") and response.citations:
                    for citation in response.citations:
                        citations.append(
                            {
                                "title": getattr(citation, "title", ""),
                                "url": getattr(citation, "url", ""),
                                "snippet": getattr(citation, "snippet", ""),
                                "datasource": (
                                    getattr(
                                        getattr(citation, "datasource", None),
                                        "name",
                                        "",
                                    )
                                    if hasattr(citation, "datasource")
                                    else ""
                                ),
                            }
                        )

            # Extract tracking token
            tracking_token = ""
            if isinstance(response, dict):
                tracking_token = response.get("tracking_token", "") or response.get(
                    "trackingToken", ""
                )
            else:
                tracking_token = getattr(response, "tracking_token", "") or getattr(
                    response, "trackingToken", ""
                )

            return {
                "query": query,
                "response": response_text,
                "citations": citations,
                "tracking_token": tracking_token,
            }

        except Exception as e:
            logger.error(f"Error formatting chat results: {e}")
            return {
                "query": query,
                "response": "",
                "error": str(e),
            }

    def format_for_llm(
        self, search_results: Dict[str, Any], use_chat: bool = False
    ) -> str:
        """Format search results for LLM consumption."""
        if search_results.get("error"):
            return f"Glean search error: {search_results['error']}"

        if use_chat and "response" in search_results:
            # Format chat response
            formatted_content = [f"**Glean Response**: {search_results['response']}"]

            # Add citations
            citations = search_results.get("citations", [])
            if citations:
                formatted_content.append("\n**Sources:**")
                for i, citation in enumerate(citations, 1):
                    title = citation.get("title", "No title")
                    url = citation.get("url", "")
                    snippet = citation.get("snippet", "")
                    datasource = citation.get("datasource", "")

                    formatted_content.append(f"{i}. **{title}**")
                    if snippet:
                        formatted_content.append(f"   {snippet}")
                    if datasource:
                        formatted_content.append(f"   Datasource: {datasource}")
                    if url:
                        formatted_content.append(f"   URL: {url}")
                    formatted_content.append("")
        else:
            # Format regular search results
            formatted_content = [
                f"**Glean Search Results for '{search_results.get('query', '')}':**",
                f"Found {search_results.get('total_results', 0)} results",
                "",
            ]

            for i, result in enumerate(search_results.get("results", []), 1):
                title = result.get("title", "No title")
                content = result.get("content", "No content")
                url = result.get("url", "")
                datasource = result.get("datasource", "")

                # Truncate content if too long
                if len(content) > 300:
                    content = content[:297] + "..."

                formatted_content.append(f"{i}. **{title}**")
                formatted_content.append(f"   {content}")
                if datasource:
                    formatted_content.append(f"   Datasource: {datasource}")
                if url:
                    formatted_content.append(f"   URL: {url}")
                formatted_content.append("")

        return "\n".join(formatted_content)

    def close(self):
        """Clean up resources."""
        if self._executor:
            self._executor.shutdown(wait=True)


# Global instance
_glean_service = None


def get_glean_service() -> GleanSearchService:
    """Get the global Glean search service instance."""
    global _glean_service
    if _glean_service is None:
        _glean_service = GleanSearchService()
    return _glean_service


async def search_glean(
    query: str,
    max_results: int = 10,
    datasources: Optional[List[str]] = None,
    use_chat: bool = False,
) -> str:
    """
    Perform Glean search.

    Args:
        query: Search query
        max_results: Number of results to return
        datasources: Specific datasources to search
        use_chat: Whether to use chat API (more conversational) or search API

    Returns:
        Formatted search results as string
    """
    service = get_glean_service()

    if use_chat:
        results = await service.chat_search(query=query)
        return service.format_for_llm(results, use_chat=True)
    else:
        results = await service.search(
            query=query,
            max_results=max_results,
            datasources=datasources,
        )
        return service.format_for_llm(results, use_chat=False)


def get_glean_search_tool() -> ChatCompletionToolParam:
    """Get the Glean search tool configuration."""
    return ChatCompletionToolParam(
        {
            "type": "function",
            "function": {
                "name": "glean_search",
                "description": "Search your organization's knowledge base using Glean. Use this for finding internal documents, company information, processes, and enterprise knowledge that may not be in the Redis knowledge base or public web.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query to find relevant information in your organization's knowledge base",
                        },
                    },
                    "required": ["query"],
                },
            },
        }
    )
