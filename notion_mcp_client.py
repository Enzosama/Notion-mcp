import os
import re
import asyncio
import json
import httpx
import logging
import subprocess
import sys
from typing import Any, Dict, List, Optional
from contextlib import asynccontextmanager
from mcp.server import NotificationOptions
from mcp.server.models import InitializationOptions
from dotenv import load_dotenv
load_dotenv()

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
except ImportError:
    raise ImportError("Please install MCP: pip install mcp")

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json"
}

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("notion-mcp-client")

def extract_uuid(resource_uri: str) -> str:
    match = re.search(r"([0-9a-f]{32})", resource_uri)
    if match:
        s = match.group(1)
        return f"{s[0:8]}-{s[8:12]}-{s[12:16]}-{s[16:20]}-{s[20:]}"
    return resource_uri

class NotionMCPClient:
    def __init__(self, server_path: str, notion_token: str):
        self.server_path = server_path
        self.notion_token = notion_token
        self.session: Optional[ClientSession] = None
        self.client = httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {self.notion_token}",
                "Notion-Version": "2022-06-28",
                "Content-Type": "application/json"
            }
        )
        
    @asynccontextmanager
    async def connect(self):
        """Connect to the Notion MCP server"""
        server_params = StdioServerParameters(
            command=sys.executable,
            args=[self.server_path],
            env={"NOTION_TOKEN": self.notion_token}
        )
        
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                self.session = session
                yield self
    
    async def list_resources(self):
        try:
            payload = {"query": ""}

            response = await self.client.post(
                "https://api.notion.com/v1/search",
                json=payload,
                headers={
                    "Authorization": f"Bearer {self.notion_token}",
                    "Notion-Version": "2022-06-28"
                }
            )
            response.raise_for_status()
            data = response.json()

            # Lấy danh sách resources (pages/databases)
            resources = data.get("results", [])
            return resources
        except Exception as e:
            logger.error(f"Error listing resources: {e}")
            raise

    async def read_resource(self, resource_uri: str):
        resource_id = extract_uuid(resource_uri)

        # 1. Lấy metadata của page
        try:
            page_resp = await self.client.get(
                f"https://api.notion.com/v1/pages/{resource_id}",
                headers={
                    "Authorization": f"Bearer {self.notion_token}",
                    "Notion-Version": "2022-06-28"
                }
            )
            page_resp.raise_for_status()
            page_data = page_resp.json()
        except Exception as e:
            logger.error(f"Error fetching page metadata: {e}")
            return

        # Lấy title
        title = ""
        properties = page_data.get("properties", {})
        for prop in properties.values():
            if prop.get("type") == "title":
                titles = prop.get("title", [])
                if titles:
                    title = titles[0].get("plain_text", "")
                break

        print(f"\nTitle: {title}\n")

        # 2. Lấy nội dung block của page
        try:
            blocks_resp = await self.client.get(
                f"https://api.notion.com/v1/blocks/{resource_id}/children?page_size=100",
                headers={
                    "Authorization": f"Bearer {self.notion_token}",
                    "Notion-Version": "2022-06-28"
                }
            )
            blocks_resp.raise_for_status()
            blocks_data = blocks_resp.json()
        except Exception as e:
            logger.error(f"Error fetching blocks content: {e}")
            return

        print("Content Blocks:")
        for block in blocks_data.get("results", []):
            btype = block.get("type")
            bcontent = block.get(btype, {}) or {}
            content = ""

            if "rich_text" in bcontent:
                content = "".join(rt.get("plain_text", "") for rt in bcontent["rich_text"])
            elif "text" in bcontent:
                content = "".join(rt.get("plain_text", "") for rt in bcontent["text"])
            elif btype == "equation": 
                content = bcontent.get("expression", "")
            elif btype == "unsupported":
                content = f"[UNSUPPORTED] {json.dumps(block, ensure_ascii=False)}"
            else:
                content = f"[{btype}]"

            print(f"- {btype}: {content}")
 
    async def list_tools(self) -> List[Dict[str, Any]]:
        """List all available tools"""
        if not self.session:
            raise RuntimeError("Client not connected")
        
        try:
            result = await self.session.list_tools()
            return [tool.model_dump() for tool in result.tools]
        except Exception as e:
            logger.error(f"Error listing tools: {e}")
            raise
    
    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> str:
        """Call a tool with the given arguments"""
        arguments = {k: v for k, v in arguments.items() if v is not None}
        logger.debug(f"Final arguments sent to tool {name}: {arguments}")
            
        result = await self.session.call_tool(name, arguments)
        return result.content[0].text if result.content else ""
    
    async def search_notion(self, query: Optional[str] = None, filter_type: Optional[str] = None) -> str:
        arguments: Dict[str, Any] = {}

        if query and query.strip():
            arguments["query"] = query.strip()
        if filter_type in ("page", "database"):
            arguments["filter"] = {"property": "object", "value": filter_type}
        logger.debug("Payload for search: %r", arguments)
        return await self.call_tool("search_notion", arguments)
    
    async def create_page(
        self, 
        title: str, 
        parent_id: str, 
        properties: Optional[Dict] = None,
        content: Optional[str] = None
    ) -> str:
        """Create a new page in Notion"""
        arguments = {
            "title": title,
            "parent_id": parent_id
        }
        if properties:
            arguments["properties"] = properties
        if content:
            arguments["content"] = content
        return await self.call_tool("create_page", arguments)
    
    async def update_page(
        self, 
        page_id: str, 
        title: Optional[str] = None,
        properties: Optional[Dict] = None
    ) -> str:
        """Update an existing page in Notion"""
        arguments = {"page_id": page_id}
        if title:
            arguments["title"] = title
        if properties:
            arguments["properties"] = properties
        return await self.call_tool("update_page", arguments)
    
    async def query_database(
        self,
        database_id: str,
        filter_criteria: Optional[Dict] = None,
        sorts: Optional[List] = None,
        page_size: Optional[int] = None
    ) -> str:
        """Query a Notion database"""
        arguments = {"database_id": database_id}
        if filter_criteria:
            arguments["filter"] = filter_criteria
        if sorts:
            arguments["sorts"] = sorts
        if page_size:
            arguments["page_size"] = page_size
        return await self.call_tool("query_database", arguments)


class NotionMCPCLI:
    """Command-line interface for the Notion MCP client"""
    
    def __init__(self, client: NotionMCPClient):
        self.client = client
        
    async def run_interactive(self):
        """Run an interactive CLI session"""
        print("Notion MCP Client - Interactive Mode")
        print("Available commands:")
        print("  list-resources    - List all available resources")
        print("  read-resource     - Read a specific resource")
        print("  list-tools        - List all available tools")
        print("  search            - Search Notion")
        print("  create-page       - Create a new page")
        print("  update-page       - Update an existing page")
        print("  query-database    - Query a database")
        print("  help              - Show this help")
        print("  quit              - Exit")
        print()
        
        while True:
            try:
                command = input("notion-mcp> ").strip().lower()
                
                if command == "quit":
                    break
                elif command == "help":
                    print("Available commands listed above")
                elif command == "list-resources":
                    await self._list_resources()
                elif command == "read-resource":
                    await self._read_resource()
                elif command == "list-tools":
                    await self._list_tools()
                elif command == "search":
                    await self._search()
                elif command == "create-page":
                    await self._create_page()
                elif command == "update-page":
                    await self._update_page()
                elif command == "query-database":
                    await self._query_database()
                else:
                    print(f"Unknown command: {command}")
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"Error: {e}")
    
    async def _list_resources(self):
        resources = await self.client.list_resources()
        print(f"\nFound {len(resources)} resources:")

        for idx, r in enumerate(resources, 1):
            if not isinstance(r, dict):
                print(f"  {idx}. [INVALID RESOURCE] {r}")
                continue

            rid = r.get("id", "")
            rtype = r.get("object", "")
            name = ""

            props = r.get("properties", {}) if rtype == "page" else (r.get("title", []) if rtype == "database" else None)

            if rtype == "page" and isinstance(props, dict):
                for prop_name, prop_value in props.items():
                    if prop_value.get("type") == "title":
                        titles = prop_value.get("title", [])
                        if titles:
                            name = titles[0].get("plain_text", "")
                        break
            elif rtype == "database" and isinstance(props, list):
                if props:
                    name = props[0].get("plain_text", "")

            url = r.get("url", "")
            print(f"  {idx}. {rtype} {rid} - {name or url}")

    async def _read_resource(self):
        """Read a specific resource"""
        uri = input("Enter resource URI: ").strip()
        if uri:
            content = await self.client.read_resource(uri)
            #print(f"\nResource content:\n{content}")
    
    async def _list_tools(self):
        """List all tools"""
        tools = await self.client.list_tools()
        print(f"\nFound {len(tools)} tools:")
        for tool in tools:
            print(f"  {tool['name']} - {tool['description']}")
    
    async def _search(self):
        """Search Notion"""
        query = input("Enter search query: ").strip() or None
        filter_type_input = input("Filter by type (page/database, or press Enter for all): ").strip()
        filter_type = filter_type_input if filter_type_input in ("page", "database") else None
        result = await self.client.search_notion(query, filter_type)
        print(f"\nSearch results:\n{result}")
        
    async def _create_page(self):
        """Create a new page"""
        title = input("Enter page title: ").strip()
        parent_id = input("Enter parent ID (page or database): ").strip()
        content = input("Enter content (markdown, optional): ").strip() or None
        
        if title and parent_id:
            result = await self.client.create_page(title, parent_id, content=content)
            print(f"\nPage created:\n{result}")
    
    async def _update_page(self):
        """Update an existing page"""
        page_id = input("Enter page ID: ").strip()
        title = input("Enter new title (optional): ").strip() or None
        
        if page_id:
            result = await self.client.update_page(page_id, title=title)
            print(f"\nPage updated:\n{result}")
    
    async def _query_database(self):
        """Query a database"""
        database_id = input("Enter database ID: ").strip()
        page_size = input("Enter page size (optional, max 100): ").strip()
        
        if database_id:
            page_size_int = int(page_size) if page_size else None
            result = await self.client.query_database(database_id, page_size=page_size_int)
            print(f"\nDatabase query results:\n{result}")
    
    async def close(self):
        await self.client.aclose()

async def main():
    """Main function"""
    import argparse
    import os
    
    parser = argparse.ArgumentParser(description="Notion MCP Client")
    parser.add_argument("--server", default="notion_mcp_server.py", help="Path to server script")
    parser.add_argument("--token", help="Notion integration token (or set NOTION_TOKEN env var)")
    parser.add_argument("--interactive", "-i", action="store_true", help="Run in interactive mode")
    
    # Example commands
    parser.add_argument("--search", help="Search query")
    parser.add_argument("--list-resources", action="store_true", help="List all resources")
    parser.add_argument("--list-tools", action="store_true", help="List all tools")
    
    args = parser.parse_args()
    
    # Get token from argument or environment
    notion_token = args.token or os.getenv("NOTION_TOKEN")
    if not notion_token:
        print("Error: Notion token is required. Use --token or set NOTION_TOKEN environment variable")
        return 1
    
    client = NotionMCPClient(args.server, notion_token)
    
    try:
        async with client.connect():
            if args.interactive:
                cli = NotionMCPCLI(client)
                await cli.run_interactive()
            elif args.search:
                result = await client.search_notion(args.search)
                print(result)
            elif args.list_resources:
                resources = await client.list_resources()
                for r in resources:
                    rid = r.get("id", "")
                    rtype = r.get("object", "")
                    name = ""
                    if rtype == "page":
                        props = r.get("properties", {})
                        for prop in props.values():
                            if prop.get("type") == "title":
                                titles = prop.get("title", [])
                                if titles:
                                    name = titles[0].get("plain_text", "")
                                break
                    elif rtype == "database":
                        titles = r.get("title", [])
                        if titles:
                            name = titles[0].get("plain_text", "")
                    url = r.get("url", "")
                    print(f"{rtype} {rid} - {name or url}")
            elif args.list_tools:
                tools = await client.list_tools()
                for tool in tools:
                    print(f"{tool['name']} - {tool['description']}")
            else:
                print("No command specified. Use --help for available options.")
                return 1
    
    except Exception as e:
        logger.error(f"Client error: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))