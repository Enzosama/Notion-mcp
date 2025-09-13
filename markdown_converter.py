import re
import mistune
from typing import List, Dict, Any

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
    
    @staticmethod
    def latex_to_notion(expr: str) -> str:
        expr = re.sub(r"\\```math([\s\S]*?)\\```", r"\1", expr)
        expr = re.sub(r"\\begin\{eqnarray\*?\}", r"\\begin{aligned}", expr)
        expr = re.sub(r"\\end\{eqnarray\*?\}", r"\\end{aligned}", expr)
        converted = expr.strip()

        return converted

    def markdown_latex_to_notion_blocks(self, content: str) -> List[Dict[str, Any]]:
        blocks: List[Dict[str, Any]] = []
        block_pattern = re.compile(r"```math(.*?)```", re.DOTALL)
        display_pattern = re.compile(r"\\```math(.*?)\\```", re.DOTALL)
        inline_pattern = re.compile(r"\$(.+?)\$")
        pos = 0
        for m in re.finditer(r"```math.*?```|\\```math.*?\\```", content, re.DOTALL):
            # Text before block
            if m.start() > pos:
                text_chunk = content[pos:m.start()]
                blocks.extend(self._process_inline_lines(text_chunk, inline_pattern))
            
            expr = m.group(0)
            expr_clean = (block_pattern.match(expr) or display_pattern.match(expr)).group(1).strip()
            expr_clean = MarkdownConverter.latex_to_notion(expr_clean)
            blocks.append({
                "object": "block",
                "type": "equation",
                "equation": {"expression": expr_clean}
            })
            pos = m.end()

        # --- Handle the remainder after last math block ---
        if pos < len(content):
            text_chunk = content[pos:]
            blocks.extend(self._process_inline_lines(text_chunk, inline_pattern))

        return blocks

    def _process_inline_lines(self, text: str, inline_pattern) -> List[Dict[str, Any]]:
        blocks = []
        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue

            parts = []
            last_idx = 0
            for m in inline_pattern.finditer(line):
                if m.start() > last_idx:
                    parts.append({
                        "type": "text",
                        "text": {"content": line[last_idx:m.start()]}
                    })
                expr = m.group(1).strip()
                expr = self.latex_to_notion(expr) 
                parts.append({
                    "type": "equation",
                    "equation": {"expression": expr}
                })
                last_idx = m.end()

            if last_idx < len(line):
                parts.append({
                    "type": "text",
                    "text": {"content": line[last_idx:]}
                })

            if len(parts) == 1 and "equation" in parts[0]:
                blocks.append({
                    "object": "block",
                    "type": "equation",
                    "equation": {"expression": parts[0]["equation"]["expression"]}
                })
            elif parts:
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {"rich_text": parts}
                })
        return blocks

    def _extract_text_content(self, rich_text_list):
        if not rich_text_list:
            return ""
        return "".join([rt.get("text", {}).get("content", "") for rt in rich_text_list if "text" in rt])    