#!/usr/bin/env python3
"""
Notion MCP Server - Example Usage and Test Script
Demonstrates how to use the Notion MCP server and client
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional
from contextlib import asynccontextmanager

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# NotionMCPClient implementation (copied to avoid circular import)
class NotionMCPClient:
    def __init__(self, server_path: str, notion_token: str):
        """
        Initialize the Notion MCP client
        
        Args:
            server_path: Path to the server script
            notion_token: Notion integration token
        """
        self.server_path = server_path
        self.notion_token = notion_token
        self.session: Optional[ClientSession] = None
        
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
    
    async def list_resources(self) -> List[Dict[str, Any]]:
        """List all available Notion resources"""
        if not self.session:
            raise RuntimeError("Client not connected")
        
        try:
            result = await self.session.list_resources()
            return [resource.model_dump() for resource in result.resources]
        except Exception as e:
            raise
    
    async def read_resource(self, uri: str) -> str:
        """Read a specific Notion resource"""
        if not self.session:
            raise RuntimeError("Client not connected")
        
        try:
            result = await self.session.read_resource(uri)
            return result.contents[0].text if result.contents else ""
        except Exception as e:
            raise
    
    async def list_tools(self) -> List[Dict[str, Any]]:
        """List all available tools"""
        if not self.session:
            raise RuntimeError("Client not connected")
        
        try:
            result = await self.session.list_tools()
            return [tool.model_dump() for tool in result.tools]
        except Exception as e:
            raise
    
    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> str:
        """Call a tool with the given arguments"""
        if not self.session:
            raise RuntimeError("Client not connected")
        
        try:
            result = await self.session.call_tool(name, arguments)
            return result.content[0].text if result.content else ""
        except Exception as e:
            raise
    
    async def search_notion(self, query: str, filter_type: Optional[str] = None) -> str:
        """Search for pages and databases in Notion"""
        arguments = {"query": query}
        if filter_type:
            arguments["filter"] = filter_type
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

class NotionMCPExample:
    def __init__(self, notion_token: str, server_path: str = "notion_mcp_server.py"):
        self.client = NotionMCPClient(server_path, notion_token)
        
    async def run_all_examples(self):
        """Run all example operations"""
        async with self.client.connect():
            print("🚀 Notion MCP Server Examples\n")
            
            # Example 1: List all resources
            await self.example_list_resources()
            
            # Example 2: List all available tools
            await self.example_list_tools()
            
            # Example 3: Search for content
            await self.example_search()
            
            # Example 4: Read a specific resource (if available)
            await self.example_read_resource()
            
            # Example 5: Query a database (if available)
            await self.example_query_database()
            
            # Example 6: Create a new page (commented out to avoid spam)
            # await self.example_create_page()
            
            print("\n✅ All examples completed!")
    
    async def example_list_resources(self):
        """Example: List all available resources"""
        print("📋 Example 1: Listing all resources")
        try:
            resources = await self.client.list_resources()
            print(f"Found {len(resources)} resources:")
            for resource in resources[:5]:  # Show first 5
                print(f"  • {resource['name']}")
                print(f"    URI: {resource['uri']}")
                print(f"    Type: {resource['mimeType']}")
                print()
            
            if len(resources) > 5:
                print(f"  ... and {len(resources) - 5} more\n")
            
        except Exception as e:
            print(f"❌ Error: {e}\n")
    
    async def example_list_tools(self):
        """Example: List all available tools"""
        print("🔧 Example 2: Listing all available tools")
        try:
            tools = await self.client.list_tools()
            print(f"Found {len(tools)} tools:")
            for tool in tools:
                print(f"  • {tool['name']}: {tool['description']}")
            print()
            
        except Exception as e:
            print(f"❌ Error: {e}\n")
    
    async def example_search(self):
        """Example: Search for content in Notion"""
        print("🔍 Example 3: Searching for content")
        try:
            # Search for pages containing "meeting"
            result = await self.client.search_notion("meeting", filter_type="page")
            print("Search results for 'meeting' (pages only):")
            
            # Parse the JSON response to show formatted results
            try:
                search_data = json.loads(result.split("Search results for")[1].split(":\n", 1)[1])
                results = search_data.get("results", [])
                
                if results:
                    for i, page in enumerate(results[:3]):  # Show first 3 results
                        title = self._extract_title(page)
                        print(f"  {i+1}. {title}")
                        print(f"     ID: {page['id']}")
                        print(f"     URL: {page.get('url', 'N/A')}")
                        print()
                else:
                    print("  No results found")
            except:
                print("  Raw search results:")
                print(f"  {result[:200]}...")
                
            print()
            
        except Exception as e:
            print(f"❌ Error: {e}\n")
    
    async def example_read_resource(self):
        """Example: Read a specific resource"""
        print("📖 Example 4: Reading a specific resource")
        try:
            # First get available resources
            resources = await self.client.list_resources()
            
            if resources:
                # Read the first page resource
                page_resources = [r for r in resources if 'page' in r['uri']]
                if page_resources:
                    resource = page_resources[0]
                    print(f"Reading resource: {resource['name']}")
                    
                    content = await self.client.read_resource(resource['uri'])
                    print("Resource content preview:")
                    print(f"  {content[:300]}...")
                    print()
                else:
                    print("  No page resources found")
            else:
                print("  No resources available")
                
        except Exception as e:
            print(f"❌ Error: {e}\n")
    
    async def example_query_database(self):
        """Example: Query a database"""
        print("🗃️  Example 5: Querying a database")
        try:
            # First find a database
            resources = await self.client.list_resources()
            db_resources = [r for r in resources if 'database' in r['uri']]
            
            if db_resources:
                database = db_resources[0]
                db_id = database['uri'].split('/')[-1]
                
                print(f"Querying database: {database['name']}")
                result = await self.client.query_database(db_id, page_size=5)
                
                print("Database query results (first 5 entries):")
                print(f"  {result[:400]}...")
                print()
            else:
                print("  No database resources found")
                
        except Exception as e:
            print(f"❌ Error: {e}\n")
    
    async def example_create_page(self):
        """Example: Create a new page (commented out by default)"""
        print("📝 Example 6: Creating a new page")
        try:
            # This example is commented out to avoid creating spam pages
            # Uncomment and modify as needed for testing
            
            # Find a parent (database or page) to create the page in
            resources = await self.client.list_resources()
            
            if resources:
                parent = resources[0]  # Use first resource as parent
                parent_id = parent['uri'].split('/')[-1]
                
                # Create a test page
                title = f"Test Page - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                content = """# Test Page

This is a test page created via the Notion MCP server.

## Features
- Markdown support
- Automatic timestamp
- MCP integration

## Notes
- Created programmatically
- Can be updated via API
- Supports rich text formatting
"""
                
                print(f"Creating page '{title}' in {parent['name']}")
                result = await self.client.create_page(
                    title=title,
                    parent_id=parent_id,
                    content=content
                )
                
                print("Page created successfully!")
                print(f"  Result: {result[:200]}...")
                print()
            else:
                print("  No parent resources available")
                
        except Exception as e:
            print(f"❌ Error: {e}\n")
    
    def _extract_title(self, page_data: dict) -> str:
        """Helper to extract page title from Notion page data"""
        try:
            # Try different ways to extract title
            if "properties" in page_data and "title" in page_data["properties"]:
                title_prop = page_data["properties"]["title"]
                if title_prop.get("title"):
                    return title_prop["title"][0].get("plain_text", "Untitled")
            elif "title" in page_data:
                if page_data["title"]:
                    return page_data["title"][0].get("plain_text", "Untitled")
            return "Untitled"
        except:
            return "Untitled"


class NotionMCPTester:
    """Test suite for the Notion MCP server"""
    
    def __init__(self, notion_token: str, server_path: str = "notion_mcp_server.py"):
        self.client = NotionMCPClient(server_path, notion_token)
        self.test_results = []
    
    async def run_tests(self):
        """Run all tests"""
        async with self.client.connect():
            print("🧪 Running Notion MCP Server Tests\n")
            
            await self.test_connection()
            await self.test_list_resources()
            await self.test_list_tools()
            await self.test_search_functionality()
            await self.test_error_handling()
            
            # Summary
            passed = sum(1 for result in self.test_results if result)
            total = len(self.test_results)
            
            print(f"\n📊 Test Results: {passed}/{total} tests passed")
            if passed == total:
                print("✅ All tests passed!")
            else:
                print("❌ Some tests failed")
    
    async def test_connection(self):
        """Test basic connection"""
        print("🔌 Testing connection...")
        try:
            # Try to list tools as a connection test
            tools = await self.client.list_tools()
            assert len(tools) > 0, "No tools available"
            print("  ✅ Connection successful")
            self.test_results.append(True)
        except Exception as e:
            print(f"  ❌ Connection failed: {e}")
            self.test_results.append(False)
    
    async def test_list_resources(self):
        """Test resource listing"""
        print("📋 Testing resource listing...")
        try:
            resources = await self.client.list_resources()
            assert isinstance(resources, list), "Resources should be a list"
            print(f"  ✅ Found {len(resources)} resources")
            self.test_results.append(True)
        except Exception as e:
            print(f"  ❌ Resource listing failed: {e}")
            self.test_results.append(False)
    
    async def test_list_tools(self):
        """Test tool listing"""
        print("🔧 Testing tool listing...")
        try:
            tools = await self.client.list_tools()
            assert isinstance(tools, list), "Tools should be a list"
            assert len(tools) >= 4, "Should have at least 4 tools"
            
            expected_tools = ["search_notion", "create_page", "update_page", "query_database"]
            tool_names = [tool['name'] for tool in tools]
            
            for expected in expected_tools:
                assert expected in tool_names, f"Missing tool: {expected}"
            
            print(f"  ✅ All {len(tools)} tools available")
            self.test_results.append(True)
        except Exception as e:
            print(f"  ❌ Tool listing failed: {e}")
            self.test_results.append(False)
    
    async def test_search_functionality(self):
        """Test search functionality"""
        print("🔍 Testing search functionality...")
        try:
            # Test basic search
            result = await self.client.search_notion("test")
            assert isinstance(result, str), "Search result should be a string"
            assert "Search results" in result, "Should contain search results"
            
            print("  ✅ Search functionality working")
            self.test_results.append(True)
        except Exception as e:
            print(f"  ❌ Search failed: {e}")
            self.test_results.append(False)
    
    async def test_error_handling(self):
        """Test error handling"""
        print("⚠️  Testing error handling...")
        try:
            # Test with invalid resource URI
            try:
                await self.client.read_resource("invalid://resource")
                # If no exception, that's unexpected
                print("  ⚠️  Expected error for invalid URI but got none")
                self.test_results.append(False)
            except Exception:
                # Expected behavior
                print("  ✅ Invalid URI handled correctly")
                
            # Test with invalid tool call
            try:
                await self.client.call_tool("nonexistent_tool", {})
                print("  ⚠️  Expected error for invalid tool but got none")
                self.test_results.append(False)
            except Exception:
                print("  ✅ Invalid tool handled correctly")
                
            self.test_results.append(True)
        except Exception as e:
            print(f"  ❌ Error handling test failed: {e}")
            self.test_results.append(False)


async def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Notion MCP Server Examples and Tests")
    parser.add_argument("--token", help="Notion integration token (or set NOTION_TOKEN env var)")
    parser.add_argument("--server", default="notion_mcp_server.py", help="Path to server script")
    parser.add_argument("--examples", action="store_true", help="Run examples")
    parser.add_argument("--tests", action="store_true", help="Run tests")
    
    args = parser.parse_args()
    
    # Get token from argument or environment
    notion_token = args.token or os.getenv("NOTION_TOKEN")
    if not notion_token:
        print(" Error: Notion token is required. Use --token or set NOTION_TOKEN environment variable")
        return 1
    
    if args.examples:
        example = NotionMCPExample(notion_token, args.server)
        await example.run_all_examples()
    elif args.tests:
        tester = NotionMCPTester(notion_token, args.server)
        await tester.run_tests()
    else:
        print("Specify --examples or --tests to run")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))