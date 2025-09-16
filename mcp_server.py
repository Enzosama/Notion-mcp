import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Sequence
from urllib.parse import urlparse
import os
from datetime import datetime
from mcp.server.models import InitializationOptions
from mcp.server import NotificationOptions
from notion_client import Client
from notion_client.errors import APIResponseError
from dotenv import load_dotenv
load_dotenv()


from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.types import (
        Resource,
        Tool,
        TextContent,
        ImageContent,
        EmbeddedResource,
    )

# Added for SSE server support
from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.requests import Request
from starlette.background import BackgroundTask
from mcp.server.sse import SseServerTransport

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("notion-mcp-server")

class NotionMCPServer:
    def __init__(self):
        # Initialize the MCP server
        self.server = Server("notion-mcp-server")
        # Initialize Notion client (will be set up after receiving token)
        self.notion_client: Optional[Client] = None
        # Setup server handlers
        self._setup_handlers()
        
    def _setup_handlers(self):
        """Setup all the MCP server handlers"""
        
        @self.server.list_resources()
        async def handle_list_resources() -> List[Resource]:
            """List available Notion resources"""
            if not self.notion_client:
                return []
            resources = []
            
            try:
                # List databases
                search_results = self.notion_client.search(filter={"object": "database"})
                for db in search_results.get("results", []):
                    resources.append(Resource(
                        uri=f"notion://database/{db['id']}",
                        name=f"Database: {db.get('title', [{}])[0].get('plain_text', 'Untitled')}",
                        description=f"Notion database with ID: {db['id']}",
                        mimeType="application/json"
                    ))
                    
                # List pages
                search_results = self.notion_client.search(filter={"object": "page"})
                for page in search_results.get("results", [])[:20]:  # Limit to 20 pages
                    title = "Untitled"
                    if "properties" in page and "title" in page["properties"]:
                        title_prop = page["properties"]["title"]
                        if title_prop.get("title"):
                            title = title_prop["title"][0].get("plain_text", "Untitled")
                    elif "title" in page:
                        if page["title"]:
                            title = page["title"][0].get("plain_text", "Untitled")
                    
                    resources.append(Resource(
                        uri=f"notion://page/{page['id']}",
                        name=f"Page: {title}",
                        description=f"Notion page with ID: {page['id']}",
                        mimeType="text/plain"
                    ))                    
            except Exception as e:
                logger.error(f"Error listing resources: {e}")
                
            return resources
            
        @self.server.read_resource()
        async def handle_read_resource(uri: str) -> str:
            """Read a specific Notion resource"""
            if not self.notion_client:
                raise ValueError("Notion client not initialized")
                
            parsed = urlparse(uri)
            if parsed.scheme != "notion":
                raise ValueError(f"Unsupported URI scheme: {parsed.scheme}")
                
            path_parts = parsed.path.strip("/").split("/")
            if len(path_parts) != 2:
                raise ValueError(f"Invalid URI format: {uri}")
                
            resource_type, resource_id = path_parts
            
            try:
                if resource_type == "database":
                    # Get database info and query its pages
                    database = self.notion_client.databases.retrieve(database_id=resource_id)
                    query_result = self.notion_client.databases.query(database_id=resource_id)
                    
                    return json.dumps({
                        "database": database,
                        "pages": query_result.get("results", [])
                    }, indent=2)
                    
                elif resource_type == "page":
                    # Get page content
                    page = self.notion_client.pages.retrieve(page_id=resource_id)
                    blocks = self.notion_client.blocks.children.list(block_id=resource_id)
                    
                    # Extract text content from blocks
                    content = self._extract_text_from_blocks(blocks.get("results", []))
                    return f"Page Content:\n{content}\n\nPage Metadata:\n{json.dumps(page, indent=2)}"
                else:
                    raise ValueError(f"Unknown resource type: {resource_type}")
            except APIResponseError as e:
                raise ValueError(f"Notion API error: {e}")
            except Exception as e:
                raise ValueError(f"Error reading resource: {e}")
                
        @self.server.list_tools()
        async def handle_list_tools() -> List[Tool]:
            """List available Notion tools"""
            return [
                Tool(
                    name="search_notion",
                    description="Search for pages and databases in Notion",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query"
                            },
                            "filter": {
                                "type": "string",
                                "enum": ["page", "database"],
                                "description": "Filter by object type (optional)"
                            }
                        },
                        "required": ["query"]
                    }
                ),
                Tool(
                    name="create_page",
                    description="Create a new page in Notion",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "title": {
                                "type": "string",
                                "description": "Page title"
                            },
                            "parent_id": {
                                "type": "string",
                                "description": "Parent page or database ID"
                            },
                            "properties": {
                                "type": "object",
                                "description": "Page properties (for database pages)"
                            },
                            "content": {
                                "type": "string",
                                "description": "Page content as markdown"
                            }
                        },
                        "required": ["title", "parent_id"]
                    }
                ),
                Tool(
                    name="update_page",
                    description="Update an existing page in Notion",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "page_id": {
                                "type": "string",
                                "description": "Page ID to update"
                            },
                            "title": {
                                "type": "string",
                                "description": "New page title (optional)"
                            },
                            "properties": {
                                "type": "object",
                                "description": "Updated page properties"
                            }
                        },
                        "required": ["page_id"]
                    }
                ),
                Tool(
                    name="query_database",
                    description="Query a Notion database with filters and sorting",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "database_id": {
                                "type": "string",
                                "description": "Database ID to query"
                            },
                            "filter": {
                                "type": "object",
                                "description": "Filter criteria"
                            },
                            "sorts": {
                                "type": "array",
                                "description": "Sort criteria"
                            },
                            "page_size": {
                                "type": "integer",
                                "description": "Number of results to return (max 100)"
                            }
                        },
                        "required": ["database_id"]
                    }
                )
            ]
            
        @self.server.call_tool()
        async def handle_call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
            """Handle tool calls"""
            if not self.notion_client:
                return [TextContent(type="text", text="Error: Notion client not initialized")]
                
            try:
                if name == "search_notion":
                    query = arguments.get("query", "")
                    filter_type = arguments.get("filter")
                    
                    search_filter = {}
                    if filter_type:
                        search_filter["object"] = filter_type
                        
                    results = self.notion_client.search(
                        query=query,
                        filter=search_filter if search_filter else None
                    )
                    
                    return [TextContent(
                        type="text",
                        text=f"Search results for '{query}':\n{json.dumps(results, indent=2)}"
                    )]
                    
                elif name == "create_page":
                    parent_id = arguments.get("parent_id")
                    properties = arguments.get("properties", {})
                    content = arguments.get("content", "")
                    
                    # Create page properties
                    page_properties = {
                        "title": {
                            "title": [{"text": {"content": arguments.get("title")}}]
                        }
                    }
                    
                    # Add additional properties if provided
                    if properties:
                        page_properties.update(properties)
                    
                    # Create the page
                    new_page = self.notion_client.pages.create(
                        parent={"page_id": parent_id} if len(parent_id) == 32 else {"database_id": parent_id},
                        properties=page_properties
                    )
                    
                    # Add content if provided
                    if content:
                        blocks = self._markdown_to_blocks(content)
                        if blocks:
                            self.notion_client.blocks.children.append(
                                block_id=new_page["id"],
                                children=blocks
                            )
                    
                    return [TextContent(
                        type="text",
                        text=f"Page created successfully:\n{json.dumps(new_page, indent=2)}"
                    )]
                    
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
                        if "properties" not in update_data:
                            update_data["properties"] = {}
                        update_data["properties"].update(properties)
                    
                    updated_page = self.notion_client.pages.update(
                        page_id=page_id,
                        **update_data
                    )
                    
                    return [TextContent(
                        type="text",
                        text=f"Page updated successfully:\n{json.dumps(updated_page, indent=2)}"
                    )]
                    
                elif name == "query_database":
                    database_id = arguments.get("database_id")
                    filter_criteria = arguments.get("filter")
                    sorts = arguments.get("sorts")
                    page_size = arguments.get("page_size", 50)
                    
                    query_params = {"database_id": database_id}
                    if filter_criteria:
                        query_params["filter"] = filter_criteria
                    if sorts:
                        query_params["sorts"] = sorts
                    if page_size:
                        query_params["page_size"] = min(page_size, 100)
                    
                    results = self.notion_client.databases.query(**query_params)
                    
                    return [TextContent(
                        type="text",
                        text=f"Database query results:\n{json.dumps(results, indent=2)}"
                    )]
                    
                else:
                    return [TextContent(type="text", text=f"Unknown tool: {name}")]
                    
            except APIResponseError as e:
                return [TextContent(type="text", text=f"Notion API error: {e}")]
            except Exception as e:
                return [TextContent(type="text", text=f"Error: {e}")]
    
    def _extract_text_from_blocks(self, blocks: List[Dict]) -> str:
        """Extract plain text from Notion blocks"""
        text_parts = []
        
        for block in blocks:
            block_type = block.get("type", "")
            
            if block_type in ["paragraph", "heading_1", "heading_2", "heading_3", "bulleted_list_item", "numbered_list_item"]:
                rich_text = block.get(block_type, {}).get("rich_text", [])
                for text_obj in rich_text:
                    text_parts.append(text_obj.get("plain_text", ""))
            elif block_type == "code":
                code_text = block.get("code", {}).get("rich_text", [])
                for text_obj in code_text:
                    text_parts.append(text_obj.get("plain_text", ""))
            
            # Handle child blocks recursively
            if block.get("has_children"):
                try:
                    children = self.notion_client.blocks.children.list(block_id=block["id"])
                    child_text = self._extract_text_from_blocks(children.get("results", []))
                    if child_text:
                        text_parts.append(child_text)
                except Exception as e:
                    logger.warning(f"Could not fetch children for block {block['id']}: {e}")
        
        return "\n".join(text_parts)
    
    def _markdown_to_blocks(self, markdown: str) -> List[Dict]:
        """Convert simple markdown to Notion blocks"""
        blocks = []
        lines = markdown.strip().split("\n")
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            if line.startswith("# "):
                blocks.append({
                    "type": "heading_1",
                    "heading_1": {
                        "rich_text": [{"type": "text", "text": {"content": line[2:]}}]
                    }
                })
            elif line.startswith("## "):
                blocks.append({
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [{"type": "text", "text": {"content": line[3:]}}]
                    }
                })
            elif line.startswith("### "):
                blocks.append({
                    "type": "heading_3",
                    "heading_3": {
                        "rich_text": [{"type": "text", "text": {"content": line[4:]}}]
                    }
                })
            elif line.startswith("- "):
                blocks.append({
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": [{"type": "text", "text": {"content": line[2:]}}]
                    }
                })
            else:
                blocks.append({
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": line}}]
                    }
                })
        
        return blocks
    
    def initialize_notion_client(self, token: str):
        """Initialize the Notion client with the provided token"""
        try:
            self.notion_client = Client(auth=token)
            logger.info("Notion client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Notion client: {e}")
            raise

# Initialize server instance and Notion client for SSE app
_server_instance = NotionMCPServer()
_notion_token = os.getenv("NOTION_TOKEN")
if _notion_token:
    _server_instance.initialize_notion_client(_notion_token)
else:
    logger.warning("NOTION_TOKEN not set. SSE endpoints will error until token is provided.")

# Configure SSE transport and Starlette app
_sse_transport = SseServerTransport("/sse/messages")

async def _sse_endpoint(request: Request):
    # Establish SSE connection and get read/write streams plus the response
    result = await _sse_transport.connect_sse(request)
    # Backwards compatibility with potential older SDK signatures
    if isinstance(result, tuple) and len(result) == 3:
        read_stream, write_stream, response = result
    else:
        # Fallback: newer SDK may return an object with attributes
        read_stream = getattr(result, "read_stream", None)
        write_stream = getattr(result, "write_stream", None)
        response = getattr(result, "response", None)
    if read_stream is None or write_stream is None or response is None:
        # If we can't unpack properly, raise a clear error
        raise RuntimeError("Failed to establish SSE connection with MCP transport")

    init_options = InitializationOptions(
        server_name="notion-mcp-server",
        server_version="1.0.0",
        capabilities=_server_instance.server.get_capabilities(
            notification_options=NotificationOptions(
                resources_changed=True,
                tools_changed=True
            ),
            experimental_capabilities=None
        )
    )

    # Run MCP server in background while returning streaming response
    response.background = BackgroundTask(
        _server_instance.server.run, read_stream, write_stream, init_options
    )
    return response

app = Starlette(routes=[
    Route("/sse", endpoint=_sse_endpoint, methods=["GET"]),
    Mount("/sse/messages", app=_sse_transport.handle_post_message),
])

async def main():
    # Get Notion token from environment variable
    notion_token = os.getenv("NOTION_TOKEN")
    if not notion_token:
        logger.error("NOTION_TOKEN environment variable is required")
        return
    
    # Create and initialize the server
    server_instance = NotionMCPServer()
    server_instance.initialize_notion_client(notion_token)
    
    # Run the server (STDIO fallback)
    from mcp.server.stdio import stdio_server
    async with stdio_server() as (read_stream, write_stream):
        await server_instance.server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="notion-mcp-server",
                server_version="1.0.0",
                capabilities=server_instance.server.get_capabilities(
                    notification_options=NotificationOptions(
                        resources_changed=True,
                        tools_changed=True
                    ),
                    experimental_capabilities=None
                )
            )
        )
if __name__ == "__main__":
    # Default to running SSE HTTP server on port 8000
    mode = os.getenv("MCP_MODE", "sse")
    if mode == "sse":
        import uvicorn
        uvicorn.run("mcp_server:app", host="0.0.0.0", port=8000)
    else:
        asyncio.run(main())