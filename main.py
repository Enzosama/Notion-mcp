import sys
import asyncio
import argparse
import os
import logging

from notion_mcp_client import NotionMCPClient, NotionMCPCLI

logger = logging.getLogger("mcp-client")
logging.basicConfig(level=logging.INFO)

async def main():
    """Notion MCP Client (JSON-RPC stdio + direct REST for resources)"""

    parser = argparse.ArgumentParser(description="Notion MCP Client")
    parser.add_argument("--server", default="mcp_server.py", help="Path to server script")
    parser.add_argument("--token", help="Notion integration token (or set NOTION_TOKEN env var)")
    parser.add_argument("--interactive", "-i", action="store_true", help="Run in interactive mode")
    parser.add_argument("--search", help="Search query")
    parser.add_argument("--list-resources", action="store_true", help="List all resources (via Notion REST)")
    parser.add_argument("--list-tools", action="store_true", help="List all tools (via JSON-RPC)")
    parser.add_argument("--create-page", nargs=2, metavar=("PARENT_ID", "TITLE"), help="Create a new page in Notion")
    parser.add_argument("--update-page", nargs=2, metavar=("PAGE_ID", "TITLE"), help="Update a Notion page title")
    parser.add_argument("--query-db", metavar="DATABASE_ID", help="Query a Notion database (simple demo)")

    args = parser.parse_args()

    # Lấy token từ arg hoặc env
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
                # Gọi trực tiếp REST API để lấy pages/databases
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

            elif args.create_page:
                parent_id, title = args.create_page
                result = await client.create_page(title, parent_id)
                print(result)

            elif args.update_page:
                page_id, title = args.update_page
                result = await client.update_page(page_id, title=title)
                print(result)

            elif args.query_db:
                db_id = args.query_db
                result = await client.query_database(db_id, page_size=5)
                print(result)

            else:
                print("No command specified. Use --help for available options.")
                return 1

    except Exception as e:
        logger.error(f"Client error: {e}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))