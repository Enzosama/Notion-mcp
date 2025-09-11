from typing import List, Dict, Any
import mistune

class MarkdownConverter:
    def __init__(self):
        self.markdown_parser = mistune.create_markdown()

    def parse_markdown_to_blocks(self, md: str) -> List[Dict[str, Any]]:
        lines = md.strip().split("\n")
        blocks = []
        # H1
        title = None
        content_start_idx = 0
        for i, line in enumerate(lines):
            if line.startswith("# "):
                title = line[2:].strip()
                content_start_idx = i + 1
                break

        if title is None:
            title = ""

        i = content_start_idx
        while i < len(lines):
            line = lines[i]

            # H2-H6
            if line.startswith("## "):
                blocks.append(
                    {
                        "type": "heading_2",
                        "heading_2": {"rich_text": [{"type": "text", "text": {"content": line[3:].strip()}}]},
                    }
                )
            elif line.startswith("### "):
                blocks.append(
                    {
                        "type": "heading_3",
                        "heading_3": {"rich_text": [{"type": "text", "text": {"content": line[4:].strip()}}]},
                    }
                )
            elif line.startswith("- "):
                blocks.append(
                    {
                        "type": "bulleted_list_item",
                        "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": line[2:].strip()}}]},
                    }
                )
            elif line.strip() and line[0].isdigit() and ". " in line:
                content = line.split(". ", 1)[1]
                blocks.append(
                    {
                        "type": "numbered_list_item",
                        "numbered_list_item": {"rich_text": [{"type": "text", "text": {"content": content.strip()}}]},
                    }
                )
            elif line.startswith("```"):
                code_lines = []
                language = line[3:].strip()
                i += 1

                while i < len(lines) and not lines[i].startswith("```"):
                    code_lines.append(lines[i])
                    i += 1

                blocks.append(
                    {
                        "type": "code",
                        "code": {
                            "rich_text": [{"type": "text", "text": {"content": "\n".join(code_lines)}}],
                            "language": language if language else "plain text",
                        },
                    }
                )
            elif line.strip():
                blocks.append(
                    {"type": "paragraph", "paragraph": {"rich_text": [{"type": "text", "text": {"content": line.strip()}}]}}
                )

            i += 1

        return blocks, title

    def convert_blocks_to_markdown(self, blocks: List[Dict[str, Any]], title: str = None) -> str:
        md_lines = []

        if title:
            md_lines.append(f"# {title}")
            md_lines.append("")  

        for block in blocks:
            block_type = block.get("type")

            if block_type == "paragraph":
                text_content = self._extract_text_content(block.get("paragraph", {}).get("rich_text", []))
                md_lines.append(text_content)
                md_lines.append("")  

            elif block_type == "heading_1":
                text_content = self._extract_text_content(block.get("heading_1", {}).get("rich_text", []))
                md_lines.append(f"# {text_content}")
                md_lines.append("")

            elif block_type == "heading_2":
                text_content = self._extract_text_content(block.get("heading_2", {}).get("rich_text", []))
                md_lines.append(f"## {text_content}")
                md_lines.append("")

            elif block_type == "heading_3":
                text_content = self._extract_text_content(block.get("heading_3", {}).get("rich_text", []))
                md_lines.append(f"### {text_content}")
                md_lines.append("")

            elif block_type == "bulleted_list_item":
                text_content = self._extract_text_content(block.get("bulleted_list_item", {}).get("rich_text", []))
                md_lines.append(f"- {text_content}")

            elif block_type == "numbered_list_item":
                text_content = self._extract_text_content(block.get("numbered_list_item", {}).get("rich_text", []))
                md_lines.append(f"1. {text_content}")

            elif block_type == "code":
                code_block = block.get("code", {})
                language = code_block.get("language", "")
                text_content = self._extract_text_content(code_block.get("rich_text", []))

                md_lines.append(f"```{language}")
                md_lines.append(text_content)
                md_lines.append("```")
                md_lines.append("")

            elif block_type == "to_do":
                todo_item = block.get("to_do", {})
                checked = todo_item.get("checked", False)
                text_content = self._extract_text_content(todo_item.get("rich_text", []))

                checkbox = "[x]" if checked else "[ ]"
                md_lines.append(f"- {checkbox} {text_content}")

            elif block_type == "quote":
                text_content = self._extract_text_content(block.get("quote", {}).get("rich_text", []))
                md_lines.append(f"> {text_content}")
                md_lines.append("")

        return "\n".join(md_lines)

    def _extract_text_content(self, rich_text_list):
        if not rich_text_list:
            return ""
        return "".join([rt.get("text", {}).get("content", "") for rt in rich_text_list if "text" in rt])