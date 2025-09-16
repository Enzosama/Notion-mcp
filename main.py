import sys
import asyncio
from notion_mcp_client import NotionMCPClient, NotionMCPCLI, logger

async def main():
    """Main function"""
    import argparse
    import os
    
    parser = argparse.ArgumentParser(description="Notion MCP Client")
    parser.add_argument("--server", default="notion_mcp_server.py", help="Path to server script")
    parser.add_argument("--token", help="Notion integration token (or set NOTION_TOKEN env var)")
    parser.add_argument("--interactive", "-i", action="store_true", help="Run in interactive mode")
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