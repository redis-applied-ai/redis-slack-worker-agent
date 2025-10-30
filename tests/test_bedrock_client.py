from app.utilities.bedrock_client import (
    map_openai_tools_to_bedrock_tool_config,
    bedrock_text_blocks_to_text,
)


def test_map_openai_tools_to_bedrock_tool_config_basic():
    openai_tools = [
        {
            "type": "function",
            "function": {
                "name": "search_knowledge_base",
                "description": "Search the KB",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "top_k": {"type": "integer", "default": 3},
                    },
                    "required": ["query"],
                },
            },
        }
    ]

    tool_config = map_openai_tools_to_bedrock_tool_config(openai_tools)

    assert "tools" in tool_config and isinstance(tool_config["tools"], list)
    assert len(tool_config["tools"]) == 1

    spec = tool_config["tools"][0]["toolSpec"]
    assert spec["name"] == "search_knowledge_base"
    assert spec["description"] == "Search the KB"
    assert spec["inputSchema"]["json"]["type"] == "object"
    assert "properties" in spec["inputSchema"]["json"]
    assert "query" in spec["inputSchema"]["json"]["properties"]


def test_map_openai_tools_handles_missing_fields():
    # Missing function data should not crash and should fall back to defaults
    openai_tools = [{}]
    tool_config = map_openai_tools_to_bedrock_tool_config(openai_tools)

    spec = tool_config["tools"][0]["toolSpec"]
    assert spec["name"] == "unknown_tool"
    assert spec["description"] == ""
    assert spec["inputSchema"]["json"]["type"] == "object"


def test_bedrock_text_blocks_to_text():
    blocks = [
        {"text": "Hello"},
        {"json": {"foo": 1}},  # Non-text block should be ignored
        {"text": "World"},
        {"toolUse": {"name": "x"}},  # Non-text block
    ]
    out = bedrock_text_blocks_to_text(blocks)
    assert out == "Hello\nWorld"

