import re
import html as py_html
from dataclasses import dataclass
from typing import List, Optional

from bot.services.formatters import convert_latex_math


@dataclass
class Segment:
    type: str  # "text" or "formula"
    content: str

    def __repr__(self) -> str:
        snippet = self.content[:30] + "..." if len(self.content) > 30 else self.content
        return f"Segment({self.type!r}, {snippet!r})"


# Complex LaTeX indicators: if an inline formula contains any of these,
# it should be rendered as a standalone image rather than squished into Unicode text.
COMPLEX_LATEX_PATTERNS = [
    r'\\(?:frac|dfrac|cfrac)(?![a-zA-Z])',
    r'\\(?:int|iint|iiint|oint|idotsint)(?![a-zA-Z])',
    r'\\(?:sum|prod|coprod)(?![a-zA-Z])',
    r'\\sqrt(?![a-zA-Z])',
    r'\\(?:begin|aligned|matrix|pmatrix|bmatrix|vmatrix|cases|array)(?![a-zA-Z])',
    r'\\\\',
    r'\\(?:lim|limsup|liminf)(?![a-zA-Z])',
    r'\\(?:partial|nabla)(?![a-zA-Z])',
]
_COMPLEX_LATEX_REGEX = re.compile("|".join(COMPLEX_LATEX_PATTERNS), re.IGNORECASE)


def is_complex_formula(formula: str) -> bool:
    """
    Determines if a LaTeX expression is complex (fractions, integrals, sums, roots, matrices)
    and should be extracted into a standalone image segment.
    """
    f = formula.strip()
    if not f:
        return False
    if _COMPLEX_LATEX_REGEX.search(f):
        return True
    # If it contains multiple division slashes with parentheses or nested exponents
    if f.count('/') >= 2 or f.count('^') >= 3:
        return True
    return False


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

    # Obvious math indicators
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


def format_text_segment_html(text: str) -> str:
    """
    Converts Markdown in a text segment to valid Telegram HTML:
    - Escapes <, >, &
    - Headers (#, ##, ###) -> <b>Header</b>
    - Bold (**bold**, __bold__) -> <b>bold</b>
    - Italic (*italic*, _italic_) -> <i>italic</i>
    - Links [text](url) -> <a href="url">text</a>
    - Blockquotes (> quote) -> <blockquote>quote</blockquote>
    - Code blocks (```lang\n...\n```) -> <pre><code class="language-lang">...</code></pre>
    - Inline code (`code`) -> <code>code</code>
    """
    if not text:
        return ""

    code_blocks = []
    inline_codes = []

    # 1. Mask code blocks
    def save_code_block(m):
        code_blocks.append(m.group(0))
        return f"\x00CODEBLOCK_{len(code_blocks)-1}\x00"

    s = re.sub(r'```([a-zA-Z0-9_\-]+)?\n?([\s\S]*?)```', save_code_block, text)

    # 2. Mask inline code
    def save_inline_code(m):
        inline_codes.append(m.group(0))
        return f"\x00INLINECODE_{len(inline_codes)-1}\x00"

    s = re.sub(r'`([^`\n]+)`', save_inline_code, s)

    # 3. Mask existing valid Telegram HTML tags
    valid_tags = []
    def save_valid_tag(m):
        valid_tags.append(m.group(0))
        return f"\x00VALIDTAG_{len(valid_tags)-1}\x00"

    s = re.sub(r'</?(?:b|i|u|s|code|pre|blockquote|a|tg-emoji)(?:\s+[^>]*?)?>', save_valid_tag, s, flags=re.IGNORECASE)

    # 4. Escape raw HTML entities
    s = py_html.escape(s, quote=False)

    # 5. Convert Markdown links: [title](url)
    s = re.sub(r'\[([^\]\n]+)\]\((https?://[^\s\)]+)\)', r'<a href="\2">\1</a>', s)

    # 6. Headers (# Header)
    s = re.sub(r'^[ \t]*#{1,6}\s+(.+)$', r'<b>\1</b>', s, flags=re.MULTILINE)

    # 7. Bold & Italic (***text***)
    s = re.sub(r'\*\*\*([^\n*]+?)\*\*\*', r'<b><i>\1</i></b>', s)

    # 8. Bold (**text** or __text__)
    s = re.sub(r'\*\*([^\n*]+?)\*\*', r'<b>\1</b>', s)
    s = re.sub(r'(?<!\w)__([^\n_]+?)__(?!\w)', r'<b>\1</b>', s)

    # 9. Italic (*text* or _text_)
    s = re.sub(r'(?<!\*)\*([^\n*]+?)\*(?!\*)', r'<i>\1</i>', s)
    s = re.sub(r'(?<![a-zA-Z0-9_])_([^\n_]+?)_(?![a-zA-Z0-9_])', r'<i>\1</i>', s)

    # 10. Quotes (> quote)
    s = re.sub(r'^[ \t]*(?:>|&gt;)\s*(.+)$', r'<blockquote>\1</blockquote>', s, flags=re.MULTILINE)

    # 11. Restore valid HTML tags
    s = re.sub(r'\x00VALIDTAG_(\d+)\x00', lambda m: valid_tags[int(m.group(1))], s)

    # 12. Restore code blocks
    def restore_code_block(m):
        raw = code_blocks[int(m.group(1))]
        match = re.match(r'```([a-zA-Z0-9_\-]+)?\n?([\s\S]*?)```', raw)
        lang = match.group(1).strip() if match and match.group(1) else ""
        content = match.group(2) if match else raw[3:-3]
        esc_content = py_html.escape(content.strip(), quote=False)
        if lang:
            return f'<pre><code class="language-{lang}">{esc_content}</code></pre>'
        return f'<pre>{esc_content}</pre>'

    s = re.sub(r'\x00CODEBLOCK_(\d+)\x00', restore_code_block, s)

    # 13. Restore inline codes
    def restore_inline_code(m):
        raw = inline_codes[int(m.group(1))]
        esc = py_html.escape(raw[1:-1], quote=False)
        return f'<code>{esc}</code>'

    s = re.sub(r'\x00INLINECODE_(\d+)\x00', restore_inline_code, s)

    # 14. Normalize consecutive blank lines
    s = re.sub(r'\n{3,}', '\n\n', s)

    return s.strip()


def split_long_text_html(html_text: str, max_chunk_size: int = 4000) -> List[str]:
    """
    Splits long HTML text at paragraph/line boundaries to stay within Telegram's 4096 limit.
    """
    if len(html_text) <= max_chunk_size:
        return [html_text]

    chunks = []
    paragraphs = html_text.split("\n\n")
    current_chunk = []
    current_len = 0

    for p in paragraphs:
        p_len = len(p) + 2
        if current_len + p_len > max_chunk_size and current_chunk:
            chunks.append("\n\n".join(current_chunk).strip())
            current_chunk = [p]
            current_len = p_len
        elif p_len > max_chunk_size:
            # Paragraph itself is too big, split by lines
            if current_chunk:
                chunks.append("\n\n".join(current_chunk).strip())
                current_chunk = []
                current_len = 0
            lines = p.split("\n")
            for line in lines:
                l_len = len(line) + 1
                if current_len + l_len > max_chunk_size and current_chunk:
                    chunks.append("\n".join(current_chunk).strip())
                    current_chunk = [line]
                    current_len = l_len
                else:
                    current_chunk.append(line)
                    current_len += l_len
        else:
            current_chunk.append(p)
            current_len += p_len

    if current_chunk:
        chunks.append("\n\n".join(current_chunk).strip())

    return [c for c in chunks if c.strip()]


def parse_response_segments(text: str) -> List[Segment]:
    """
    Parses LLM response into an ordered sequence of 'text' and 'formula' segments.
    - Code blocks (```...```) and inline code (`...`) are protected from math parsing.
    - Currency prices ($5, $10) are preserved in text.
    - Block formulas ($$...$$ and \\[...\\]) become separate 'formula' segments.
    - Complex inline formulas ($...$ with frac, int, sum, sqrt) become 'formula' segments.
    - Simple inline formulas ($...$ like x^2, \\alpha, \\approx) are converted to Unicode in text.
    - Strict segment ordering is maintained.
    - Consecutive text segments are merged. Empty text segments are omitted.
    - Long text segments (>4000 chars) are divided into paragraph-friendly chunks.
    """
    if not text:
        return []

    # Step 1: Protect code blocks and inline code
    code_blocks = []
    inline_codes = []

    def save_cb(m):
        code_blocks.append(m.group(0))
        return f"\x00CODEBLOCK_{len(code_blocks)-1}\x00"

    clean_text = re.sub(r'```(?:[a-zA-Z0-9_\-]+)?\n?[\s\S]*?```', save_cb, text)

    def save_ic(m):
        inline_codes.append(m.group(0))
        return f"\x00INLINECODE_{len(inline_codes)-1}\x00"

    clean_text = re.sub(r'`[^`\n]+`', save_ic, clean_text)

    # Step 2: Combined regex to find all math tokens in order of precedence:
    # 1) $$ ... $$
    # 2) \[ ... \]
    # 3) \( ... \)
    # 4) $ ... $
    math_pattern = re.compile(
        r'(?P<block_dollar>\$\$([\s\S]*?)\$\$)|'
        r'(?P<block_bracket>\\\[([\s\S]*?)\\\])|'
        r'(?P<inline_paren>\\\(([\s\S]+?)\\\))|'
        r'(?P<inline_dollar>(?<![\\\$])\$(?!\s)([^\$\n]+?)(?<!\s)(?<!\\)\$)',
        re.MULTILINE
    )

    raw_segments: List[Segment] = []
    last_idx = 0

    def restore_code_tokens(s: str) -> str:
        s = re.sub(r'\x00CODEBLOCK_(\d+)\x00', lambda m: code_blocks[int(m.group(1))], s)
        s = re.sub(r'\x00INLINECODE_(\d+)\x00', lambda m: inline_codes[int(m.group(1))], s)
        return s

    for match in math_pattern.finditer(clean_text):
        start, end = match.span()

        # Check matched group
        is_block = False
        formula_content = None

        if match.group('block_dollar'):
            formula_content = match.group(2).strip()
            is_block = True
        elif match.group('block_bracket'):
            formula_content = match.group(4).strip()
            is_block = True
        elif match.group('inline_paren'):
            formula_content = match.group(6).strip()
        elif match.group('inline_dollar'):
            raw_inner = match.group(8).strip()
            if not is_likely_math(raw_inner):
                # It's a currency or false positive, skip and treat as normal text
                continue
            formula_content = raw_inner

        if formula_content is None:
            continue

        # Text before this formula
        text_before = clean_text[last_idx:start]

        if is_block or is_complex_formula(formula_content):
            # This formula should be a separate 'formula' segment!
            if text_before:
                raw_segments.append(Segment(type="text", content=text_before))
            raw_segments.append(Segment(type="formula", content=formula_content))
            last_idx = end
        else:
            # Simple formula: convert to Unicode in-place!
            unicode_math = convert_latex_math(formula_content)
            # Replace in text stream by appending to text_before and continuing
            raw_segments.append(Segment(type="text", content=text_before + unicode_math))
            last_idx = end

    # Trailing text after the last formula
    if last_idx < len(clean_text):
        remaining = clean_text[last_idx:]
        if remaining:
            raw_segments.append(Segment(type="text", content=remaining))

    # Step 3: Merge adjacent text segments and strip empty segments
    merged_segments: List[Segment] = []
    current_text_parts = []

    for seg in raw_segments:
        if seg.type == "text":
            current_text_parts.append(seg.content)
        else:
            # We hit a formula segment
            if current_text_parts:
                combined_text = "".join(current_text_parts)
                combined_text = restore_code_tokens(combined_text)
                if combined_text.strip():
                    merged_segments.append(Segment(type="text", content=combined_text.strip()))
                current_text_parts = []
            if seg.content.strip():
                merged_segments.append(Segment(type="formula", content=seg.content.strip()))

    if current_text_parts:
        combined_text = "".join(current_text_parts)
        combined_text = restore_code_tokens(combined_text)
        if combined_text.strip():
            merged_segments.append(Segment(type="text", content=combined_text.strip()))

    # Step 4: Format text segments into Telegram HTML and split chunks >4000 chars
    final_segments: List[Segment] = []
    for seg in merged_segments:
        if seg.type == "formula":
            final_segments.append(seg)
        else:
            html_text = format_text_segment_html(seg.content)
            # If the segment contains no letters or digits (e.g. only trailing punctuation like '.' or ',')
            if not html_text.strip() or not re.search(r'[\wА-Яа-яЁё]', html_text):
                continue
            chunks = split_long_text_html(html_text, max_chunk_size=4000)
            for chunk in chunks:
                if chunk.strip() and re.search(r'[\wА-Яа-яЁё]', chunk):
                    final_segments.append(Segment(type="text", content=chunk.strip()))

    return final_segments
