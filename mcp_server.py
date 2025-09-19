"""
mcp_server.py

MCP Server cho Notion chạy theo JSON-RPC 2.0 qua stdin/stdout.
Không dùng HTTP/SSE, chỉ cần giao tiếp stdio với client.
"""

import sys
import json
import logging
import os
from typing import Any, Dict, List, Optional

from notion_client import Client
from notion_client.errors import APIResponseError
from dotenv import load_dotenv

# Load env file
load_dotenv()


class MCPServer:
    def __init__(self, token: Optional[str] = None):
        """Khởi tạo MCP Server với Notion token"""
        self.logger = logging.getLogger("mcp-server-jsonrpc")
        logging.basicConfig(level=logging.INFO)

        token = token or os.getenv("NOTION_TOKEN")
        if not token:
            raise RuntimeError("NOTION_TOKEN environment variable is required")

        self.notion = Client(auth=token)

    # ------------------ Main loop ------------------

    def start(self):
        """Chạy vòng lặp đọc request qua stdin, trả về response qua stdout"""
        self.logger.info("Starting Notion MCP JSON-RPC server (stdio mode)")
        while True:
            line = sys.stdin.readline()
            if not line:
                break
            try:
                request = json.loads(line)
                self._handle_request(request)
            except json.JSONDecodeError:
                self._send_error(-32700, "Parse error", None)

    # ------------------ Request routing ------------------

    def _handle_request(self, request: Dict[str, Any]):
        rid = request.get("id")
        method = request.get("method")
        params = request.get("params", {})

        if method == "initialize":
            self._handle_initialize(params, rid)
        elif method == "tools/list":
            self._handle_tools_list(rid)
        elif method == "tools/call":
            self._handle_tools_call(params, rid)
        else:
            self._send_error(-32601, f"Unknown method: {method}", rid)

    # ------------------ Methods ------------------

    def _handle_initialize(self, params: Dict[str, Any], rid: Any):
        result = {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "notion-mcp-jsonrpc", "version": "1.0.0", "description": "JSON-RPC MCP Server for Notion"},
                "capabilities": {
                    "tools": {"listChanged": False},
                    "resources": {"listChanged": False, "subscribe": False}
                },
            }
        
        self._send_result(result, rid)
        # Gửi danh sách tools ban đầu
        self._send_response({
            "jsonrpc": "2.0",
            "method": "notifications/tools/list_changed",
            "params": None
        })

    def _handle_tools_list(self, rid: Any):
        """Xử lý tools/list"""
        self._send_result({"tools": self._get_tools()}, rid)

    def _handle_tools_call(self, params: Dict[str, Any], rid: Any):
        """Xử lý tools/call"""
        name = params.get("name")
        arguments = params.get("arguments", {})

        if not name:
            self._send_error(-32602, "Invalid params: name is required", rid)
            return

        try:
            if name == "search_notion":
                query = arguments.get("query", "")
                filt = arguments.get("filter")
                filter_dict = {"object": filt} if filt else None
                results = self.notion.search(query=query, filter=filter_dict)
                self._send_tool_result(results, rid)

            elif name == "create_page":
                parent_id = arguments.get("parent_id")
                title = arguments.get("title", "")
                properties = arguments.get("properties", {})
                content = arguments.get("content", "")

                page_properties = {
                    "title": {"title": [{"text": {"content": title}}]}
                }
                if properties:
                    page_properties.update(properties)

                # Parent có thể là page hoặc database
                parent = {"page_id": parent_id} if len(parent_id) == 32 else {"database_id": parent_id}

                new_page = self.notion.pages.create(parent=parent, properties=page_properties)

                # Nếu có content markdown thì thêm vào
                if content:
                    blocks = self._markdown_to_blocks(content)
                    if blocks:
                        self.notion.blocks.children.append(
                            block_id=new_page["id"],
                            children=blocks
                        )

                self._send_tool_result(new_page, rid)

            elif name == "update_page":
                page_id = arguments.get("page_id")
                title = arguments.get("title")
                properties = arguments.get("properties", {})

                update_data = {}
                if title:
                    update_data["properties"] = {
                        "title": {
                            "title": [{"text": {"content": title}}]
                        }
                    }
                if properties:
                    update_data.setdefault("properties", {}).update(properties)

                updated_page = self.notion.pages.update(page_id=page_id, **update_data)
                self._send_tool_result(updated_page, rid)

            elif name == "query_database":
                database_id = arguments["database_id"]
                filter_criteria = arguments.get("filter")
                sorts = arguments.get("sorts")
                page_size = min(arguments.get("page_size", 50), 100)

                query_params = {"database_id": database_id}
                if filter_criteria:
                    query_params["filter"] = filter_criteria
                if sorts:
                    query_params["sorts"] = sorts
                query_params["page_size"] = page_size

                results = self.notion.databases.query(**query_params)
                self._send_tool_result(results, rid)

            else:
                self._send_result(
                    {"content": [{"type": "text", "text": f"Unknown tool: {name}"}], "isError": True},
                    rid
                )
        except APIResponseError as e:
            self._send_result({"content": [{"type": "text", "text": f"Notion API error: {str(e)}"}], "isError": True}, rid)
        except Exception as e:
            self._send_result({"content": [{"type": "text", "text": f"Error: {str(e)}"}], "isError": True}, rid)

    # ------------------ Tool definitions ------------------

    def _get_tools(self) -> List[Dict[str, Any]]:
        """Danh sách tools khả dụng"""
        return [
            {
                "name": "search_notion",
                "description": "Search for pages and databases in Notion",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                        "filter": {"type": "string", "enum": ["page", "database"]}
                    },
                    "required": ["query"]
                }
            },
            {
                "name": "create_page",
                "description": "Create a new Notion page",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "parent_id": {"type": "string"},
                        "properties": {"type": "object"},
                        "content": {"type": "string"}
                    },
                    "required": ["title", "parent_id"]
                }
            },
            {
                "name": "update_page",
                "description": "Update an existing Notion page",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "page_id": {"type": "string"},
                        "title": {"type": "string"},
                        "properties": {"type": "object"}
                    },
                    "required": ["page_id"]
                }
            },
            {
                "name": "query_database",
                "description": "Query a Notion database",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "database_id": {"type": "string"},
                        "filter": {"type": "object"},
                        "sorts": {"type": "array"},
                        "page_size": {"type": "integer"}
                    },
                    "required": ["database_id"]
                }
            }
        ]

    # ------------------ Helpers ------------------

    def _markdown_to_blocks(self, markdown: str) -> List[Dict]:
        """Convert simple markdown text into Notion blocks"""
        blocks = []
        lines = markdown.strip().split("\n")
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if line.startswith("# "):
                blocks.append({"type": "heading_1", "heading_1": {"rich_text": [{"type": "text", "text": {"content": line[2:]}}]}})
            elif line.startswith("## "):
                blocks.append({"type": "heading_2", "heading_2": {"rich_text": [{"type": "text", "text": {"content": line[3:]}}]}})
            elif line.startswith("### "):
                blocks.append({"type": "heading_3", "heading_3": {"rich_text": [{"type": "text", "text": {"content": line[4:]}}]}})
            elif line.startswith("- "):
                blocks.append({"type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": line[2:]}}]}})
            else:
                blocks.append({"type": "paragraph", "paragraph": {"rich_text": [{"type": "text", "text": {"content": line}}]}})
        return blocks

    def _send_tool_result(self, data: Any, rid: Any):
        """Đóng gói data trả về theo chuẩn MCP content"""
        text = json.dumps(data, indent=2, ensure_ascii=False)
        self._send_result({"content": [{"type": "text", "text": text}]}, rid)

    def _send_result(self, result: Any, rid: Any):
        response = {"jsonrpc": "2.0", "result": result, "id": rid}
        self._send_response(response)

    def _send_error(self, code: int, message: str, rid: Any):
        response = {"jsonrpc": "2.0", "error": {"code": code, "message": message}, "id": rid}
        self._send_response(response)

    def _send_response(self, resp: Dict[str, Any]):
        print(json.dumps(resp, ensure_ascii=False), flush=True)
        self.logger.info(f"Sent response: {resp}")


# ------------------ Entry ------------------

if __name__ == "__main__":
    server = MCPServer()
    server.start()