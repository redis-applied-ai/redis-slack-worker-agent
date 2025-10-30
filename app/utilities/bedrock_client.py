import os
import logging
from typing import Any, Dict, List, Optional

import boto3

logger = logging.getLogger(__name__)

_bedrock_client = None


def get_bedrock_runtime_client():
    global _bedrock_client
    if _bedrock_client is None:
        region = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
        _bedrock_client = boto3.client("bedrock-runtime", region_name=region)
    return _bedrock_client


def map_openai_tools_to_bedrock_tool_config(openai_tools: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Convert OpenAI-style tools definitions to Bedrock Converse toolConfig.

    Expected OpenAI-style entry shape:
      {"type": "function", "function": {"name": str, "description": str, "parameters": { ... }}}
    """
    tools_out: List[Dict[str, Any]] = []
    for t in openai_tools:
        fn = (t or {}).get("function", {})
        name = fn.get("name", "unknown_tool")
        description = fn.get("description") or ""
        # Parameters is already a JSON schema; pass through
        params = fn.get("parameters") or {"type": "object", "properties": {}}
        tools_out.append(
            {
                "toolSpec": {
                    "name": name,
                    "description": description,
                    "inputSchema": {"json": params},
                }
            }
        )
    return {"tools": tools_out}


def bedrock_text_blocks_to_text(content_blocks: List[Dict[str, Any]]) -> str:
    parts: List[str] = []
    for block in content_blocks or []:
        if isinstance(block, dict) and "text" in block:
            parts.append(block.get("text") or "")
    return "\n".join(p for p in parts if p)

