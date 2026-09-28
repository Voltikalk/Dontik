import re
import html as py_html
from typing import List, Tuple
from tg_rich_converter import balance_streaming_markdown


def is_likely_math(content: str) -> bool:
    """
    Checks whether a string enclosed in $...$ is actual LaTeX math
    as opposed to prices (e.g. '$5 and $10'), currencies, or plain text with dollar signs.
    """
    s = content.strip()
    if not s:
        return False

    # Cannot start or end with spaces in LaTeX inline math ($ math $)
    if content.startswith(' ') or content.endswith(' '):
        return False

    # If it's a bare number or currency amount like "5", "10.50", "1,000", not math
    if re.match(r'^\d+([.,]\d+)?$', s):
        return False

    # If it's a range like "5 to 10" or "5 - 10" or "5 and 10" without math operators
    if re.match(r'^\d+([.,]\d+)?\s*(?:to|and|или|и|-|—|до)\s*\$?\d+([.,]\d+)?$', s, re.IGNORECASE):
        return False

    # Obvious math indicators: backslashes, superscripts, subscripts, operators
    if any(char in s for char in ['\\', '^', '_', '=', '<', '>', '±', '≠', '≤', '≥', '×', '·', '∫', '∑', '√']):
        return True

    # Standard math variables / simple functions: e.g. x, y, x + y, a/b, 2x, f(x), \alpha
    if re.match(r'^[a-zA-Z0-9\s\+\-\*/\(\)\,\.]+$', s):
        # Has an operator or single variable
        if any(op in s for op in ['+', '-', '*', '/', '(', ')']):
            return True
        # Single variable like "x", "n", "k"
        if len(s) == 1 and s.isalpha():
            return True

    return False


def format_inline_markdown(text: str) -> str:
    """
    Converts inline Markdown styles (*, **, __, ~~, [link](url)) to HTML tags.
    Raw HTML entities (<, >, &) are safely escaped.
    """
    if not text:
        return ""

    # 1. Escape HTML special characters
    s = py_html.escape(text, quote=False)

    # 2. Markdown links: [text](url)
    s = re.sub(r'\[([^\]\n]+)\]\((https?://[^\s\)]+)\)', r'<a href="\2">\1</a>', s)

    # 3. Bold + Italic: ***text***
    s = re.sub(r'\*\*\*([^\n*]+?)\*\*\*', r'<b><i>\1</i></b>', s)

    # 4. Bold: **text** or __text__
    s = re.sub(r'\*\*([^\n*]+?)\*\*', r'<b>\1</b>', s)
    s = re.sub(r'(?<!\w)__([^\n_]+?)__(?!\w)', r'<b>\1</b>', s)

    # 5. Italic: *text* or _text_
    s = re.sub(r'(?<!\*)\*([^\n*]+?)\*(?!\*)', r'<i>\1</i>', s)
    s = re.sub(r'(?<![a-zA-Z0-9_])_([^\n_]+?)_(?![a-zA-Z0-9_])', r'<i>\1</i>', s)

    # 6. Strikethrough: ~~text~~
    s = re.sub(r'~~([^\n~]+?)~~', r'<s>\1</s>', s)

    # 7. Spoiler: ||text||
    s = re.sub(r'\|\|([^\n\|]+?)\|\|', r'<tg-spoiler>\1</tg-spoiler>', s)

    return s


def markdown_to_rich_html(text: str, streaming: bool = False) -> str:
    """
    Converts Markdown + LaTeX text to native Telegram Rich HTML (Bot API 10.1+):
    - Block formulas $$...$$ and \\[...\\] -> <tg-math-block>LaTeX</tg-math-block>
    - Inline formulas $...$ and \\(...\\) -> <tg-math>LaTeX</tg-math>
    - Code blocks (```...```) -> <pre><code class="language-...">...</code></pre>
    - Inline code (`...`) -> <code>...</code>
    - Headings (#, ##, ###) -> <h1>, <h2>, <h3>
    - Numbered headings (e.g. 1. **Title** or 1. Title) -> <b>1. Title</b>
    - Lists (unordered/ordered) -> <ul>, <ol>, <li>
    - Tables -> <table bordered="true" striped="true">...</table>
    - Blockquotes -> <blockquote>...</blockquote>
    - Preserves $ in code and prices like $5.
    - All LaTeX formulas and text have <, >, & safely escaped.
    """
    if not text:
        return ""

    if streaming:
        text = balance_streaming_markdown(text)

    # Normalize line breaks
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    placeholders: List[str] = []

    def save_placeholder(content: str) -> str:
        idx = len(placeholders)
        placeholders.append(content)
        return f"\x00RICH_{idx}\x00"

    # Step 1: Protect code blocks
    def replace_code_block(m: re.Match) -> str:
        lang = (m.group(1) or "").strip()
        code_content = m.group(2).strip("\n")
        esc_code = py_html.escape(code_content, quote=False)
        if lang:
            esc_lang = py_html.escape(lang, quote=False)
            rendered = f'<pre><code class="language-{esc_lang}">{esc_code}</code></pre>'
        else:
            rendered = f'<pre><code>{esc_code}</code></pre>'
        return save_placeholder(rendered)

    text = re.sub(r'```([a-zA-Z0-9_\-\+]*)\n([\s\S]*?)```', replace_code_block, text)

    # Step 2: Protect inline code
    def replace_inline_code(m: re.Match) -> str:
        code_content = m.group(1)
        esc_code = py_html.escape(code_content, quote=False)
        return save_placeholder(f'<code>{esc_code}</code>')

    text = re.sub(r'`([^`\n]+)`', replace_inline_code, text)

    # Step 3: Block LaTeX formulas ($$...$$ and \[...\])
    def replace_math_block(m: re.Match) -> str:
        raw_formula = m.group(1).strip()
        # Escape <, >, & inside formula as required by Telegram Rich HTML
        esc_formula = py_html.escape(raw_formula, quote=False)
        rendered = f"<tg-math-block>{esc_formula}</tg-math-block>"
        return f"\n{save_placeholder(rendered)}\n"

    text = re.sub(r'\$\$([\s\S]*?)\$\$', replace_math_block, text)
    text = re.sub(r'\\\[([\s\S]*?)\\\]', replace_math_block, text)

    # Step 4: Inline LaTeX formulas ($...$ and \(...\))
    def replace_inline_math(m: re.Match) -> str:
        raw_formula = m.group(1).strip()
        if not is_likely_math(raw_formula):
            return m.group(0)
        esc_formula = py_html.escape(raw_formula, quote=False)
        rendered = f"<tg-math>{esc_formula}</tg-math>"
        return save_placeholder(rendered)

    # Match $...$ where $ is not doubled, not followed/preceded by space
    text = re.sub(r'(?<![\\\$])\$(?!\s)([^\$\n]+?)(?<!\s)(?<!\\)\$', replace_inline_math, text)
    text = re.sub(r'\\\(([\s\S]+?)\\\)', replace_inline_math, text)

    # Step 5: Markdown tables (| col1 | col2 |)
    lines = text.split("\n")
    processed_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]
        # Check if table header
        if (
            "|" in line
            and i + 1 < len(lines)
            and re.match(r"^[\s\|:\-]+$", lines[i + 1])
            and "-" in lines[i + 1]
        ):
            table_lines = [line, lines[i + 1]]
            i += 2
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                table_lines.append(lines[i])
                i += 1
            # Render table
            rendered_table = _render_table(table_lines)
            processed_lines.append(save_placeholder(rendered_table))
        else:
            processed_lines.append(line)
            i += 1

    text = "\n".join(processed_lines)

    # Step 6: Numbered Headings (e.g. "1. **Ряд Софуса**" or "1. Ряд Софуса")
    # Must remain bold headings rather than being swallowed into nested lists
    def replace_numbered_heading(m: re.Match) -> str:
        num = m.group(1)
        bold_content = m.group(2).strip()
        rest = m.group(3)
        formatted_content = format_inline_markdown(bold_content)
        formatted_rest = format_inline_markdown(rest)
        return save_placeholder(f"<b>{num} {formatted_content}</b>{formatted_rest}")

    text = re.sub(
        r'^[ \t]*(\d+\.)\s+\*\*([^\*\n]+)\*\*(.*)$',
        replace_numbered_heading,
        text,
        flags=re.MULTILINE
    )

    # Step 7: Markdown Headings (# Header)
    def replace_heading(m: re.Match) -> str:
        level = min(len(m.group(1)), 6)
        content = format_inline_markdown(m.group(2).strip())
        return save_placeholder(f"<h{level}>{content}</h{level}>")

    text = re.sub(r'^[ \t]*(#{1,6})\s+(.+)$', replace_heading, text, flags=re.MULTILINE)

    # Step 8: Lists (unordered * / - / •, and standard ordered 1.)
    lines = text.split("\n")
    new_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]
        ul_match = re.match(r'^[ \t]*([•\-\*])\s+(.+)$', line)
        ol_match = re.match(r'^[ \t]*(\d+\.)\s+(.+)$', line)

        if ul_match and not "\x00RICH_" in line:
            items = [ul_match.group(2)]
            i += 1
            while i < len(lines):
                next_item = re.match(r'^[ \t]*[•\-\*]\s+(.+)$', lines[i])
                if next_item and not "\x00RICH_" in lines[i]:
                    items.append(next_item.group(1))
                    i += 1
                else:
                    break
            rendered_items = [f"  <li>{format_inline_markdown(it)}</li>" for it in items]
            html_list = "<ul>\n" + "\n".join(rendered_items) + "\n</ul>"
            new_lines.append(save_placeholder(html_list))
        elif ol_match and not "\x00RICH_" in line:
            items = [ol_match.group(2)]
            i += 1
            while i < len(lines):
                next_item = re.match(r'^[ \t]*\d+\.\s+(.+)$', lines[i])
                if next_item and not "\x00RICH_" in lines[i]:
                    items.append(next_item.group(1))
                    i += 1
                else:
                    break
            rendered_items = [f"  <li>{format_inline_markdown(it)}</li>" for it in items]
            html_list = "<ol>\n" + "\n".join(rendered_items) + "\n</ol>"
            new_lines.append(save_placeholder(html_list))
        else:
            new_lines.append(line)
            i += 1

    text = "\n".join(new_lines)

    # Step 9: Blockquotes (> quote)
    def replace_quote(m: re.Match) -> str:
        raw_lines = [l.lstrip('>').strip() for l in m.group(0).split('\n') if l.strip()]
        content = "\n".join(format_inline_markdown(l) for l in raw_lines)
        return save_placeholder(f"<blockquote>{content}</blockquote>")

    text = re.sub(r'^(?:[ \t]*>.*(?:\n|$))+', replace_quote, text, flags=re.MULTILINE)

    # Step 10: Format remaining inline text (paragraphs, bold, italic, links, escaping)
    # Split by placeholders so we only format text outside placeholders
    parts = re.split(r'(\x00RICH_\d+\x00)', text)
    formatted_parts = []
    for part in parts:
        if part.startswith('\x00RICH_') and part.endswith('\x00'):
            formatted_parts.append(part)
        else:
            formatted_parts.append(format_inline_markdown(part))

    text = "".join(formatted_parts)

    # Step 11: Restore placeholders
    while "\x00RICH_" in text:
        prev_text = text
        for idx, repl in enumerate(placeholders):
            key = f"\x00RICH_{idx}\x00"
            if key in text:
                text = text.replace(key, repl)
        if text == prev_text:
            break

    # Normalize excessive newlines
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _render_table(lines: List[str]) -> str:
    """Renders a Markdown pipe-table into Rich HTML <table bordered="true" striped="true">."""
    header_cells = [c.strip() for c in lines[0].strip().strip("|").split("|")]
    align_cells = [c.strip() for c in lines[1].strip().strip("|").split("|")]

    alignments = []
    for a in align_cells:
        if a.startswith(":") and a.endswith(":"):
            alignments.append(' align="center"')
        elif a.endswith(":"):
            alignments.append(' align="right"')
        elif a.startswith(":"):
            alignments.append(' align="left"')
        else:
            alignments.append("")

    html_out = ['<table bordered="true" striped="true">']
    html_out.append("  <thead><tr>")
    for idx, col in enumerate(header_cells):
        align = alignments[idx] if idx < len(alignments) else ""
        content = format_inline_markdown(col)
        html_out.append(f"    <th{align}>{content}</th>")
    html_out.append("  </tr></thead>")

    html_out.append("  <tbody>")
    for row_str in lines[2:]:
        cells = [c.strip() for c in row_str.strip().strip("|").split("|")]
        html_out.append("    <tr>")
        for idx, c in enumerate(cells):
            align = alignments[idx] if idx < len(alignments) else ""
            content = format_inline_markdown(c)
            html_out.append(f"      <td{align}>{content}</td>")
        html_out.append("    </tr>")
    html_out.append("  </tbody>")
    html_out.append("</table>")
    return "\n".join(html_out)


def split_rich_message(html_text: str, max_limit: int = 32000) -> List[str]:
    """
    Splits Rich HTML message if it exceeds the 32,768 character limit.
    Splits only at paragraph boundaries and never in the middle of <tg-math-block> or tags.
    """
    if len(html_text) <= max_limit:
        return [html_text]

    chunks: List[str] = []
    paragraphs = html_text.split("\n\n")
    current_chunk = []
    current_len = 0

    for p in paragraphs:
        p_len = len(p) + 2
        if current_len + p_len > max_limit and current_chunk:
            chunks.append("\n\n".join(current_chunk).strip())
            current_chunk = [p]
            current_len = p_len
        else:
            current_chunk.append(p)
            current_len += p_len

    if current_chunk:
        chunks.append("\n\n".join(current_chunk).strip())

    return [c for c in chunks if c.strip()]
