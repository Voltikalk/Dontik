import re
import html as py_html
from typing import List, Tuple

try:
    from tg_rich_converter import balance_streaming_markdown
except ImportError:
    def balance_streaming_markdown(s: str) -> str:
        return s


def clean_squished_bullets(text: str) -> str:
    """
    Разделяет строки, где элементы списка слиплись в одну строку через '•' или '·'.
    Например: 'Кинематика: • Скорость: $v = at$ • Перемещение: $s = vt$'
    Превращает в:
    Кинематика:
    - Скорость: $v = at$
    - Перемещение: $s = vt$
    При этом сохраняет строку источников: '🔗 Источники: [A](url) • [B](url)'
    """
    lines = text.split("\n")
    out_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            out_lines.append("")
            continue

        # Не разбиваем строку с источниками
        if re.search(r'Источники:.*', line, re.IGNORECASE):
            out_lines.append(line)
            continue

        # Если в строке 2 или более маркеров списка '•' или '·'
        bullet_count = line.count("•") + line.count("·")
        if bullet_count >= 2 or ("•" in line and not line.lstrip().startswith(("•", "·"))):
            parts = re.split(r'\s*[•·]\s*', line)
            parts = [p.strip() for p in parts if p.strip()]
            if parts:
                first = parts[0]
                if not line.lstrip().startswith(("•", "·")):
                    out_lines.append(first)
                    for item in parts[1:]:
                        out_lines.append(f"- {item}")
                else:
                    for item in parts:
                        out_lines.append(f"- {item}")
                continue

        # Одиночный маркер '•' или '·' в начале строки нормализуем в Markdown '- '
        m = re.match(r'^(\s*)[•·]\s*(.*)$', line)
        if m:
            indent = m.group(1)
            content = m.group(2)
            out_lines.append(f"{indent}- {content}")
            continue

        out_lines.append(line)
    return "\n".join(out_lines)


_MATH_MARKERS = (
    '\\', '^', '_', '=', '<', '>', '±', '≠', '≤', '≥', '≈', '×', '÷', '·',
    '∫', '∑', '∏', '√', '∞', '∂', '∇', '⇒', '→', '∈', '∑', '{', '}',
    '∈', '≡', '⊂', '°', 'π', 'α', 'β', 'γ', 'ω', 'λ', 'μ', 'σ', 'φ', 'Ω',
)

_MATH_COMMANDS = (
    'frac', 'sqrt', 'int', 'sum', 'prod', 'lim', 'log', 'ln', 'exp', 'sin',
    'cos', 'tan', 'left', 'right', 'cdot', 'times', 'leq', 'geq', 'neq',
    'pmatrix', 'bmatrix', 'cases', 'partial', 'nabla', 'infty', 'begin', 'end',
)


def is_likely_math(content: str) -> bool:
    """
    Проверяет, является ли содержимое между $...$ математической формулой,
    а не денежной суммой вроде «$5» или «$10.99».
    """
    s = content.strip()
    if not s or content.startswith(' ') or content.endswith(' '):
        return False

    # Просто число или денежная сумма ("5", "10.50", "1,000")
    if re.match(r'^\d+([.,]\d+)?$', s):
        return False

    # Диапазон цен ("5 to 10", "5 - 10", "5 and 10")
    if re.match(r'^\d+([.,]\d+)?\s*(?:to|and|или|и|-|—|до|\.\.)\s*\$?\d+([.,]\d+)?$', s, re.IGNORECASE):
        return False

    # Явные математические символы и фигурные скобки (LaTeX-группировка)
    if any(char in s for char in _MATH_MARKERS):
        return True

    # Известные LaTeX-команды
    lowered = s.lower()
    if any(re.search(rf'\\{cmd}\b', lowered) for cmd in _MATH_COMMANDS):
        return True

    # Переменные и операторы: a+b, x1/2, 2(x+1)
    if re.match(r'^[a-zA-Z0-9\s\+\-\*/\(\)\,\.\!]+$', s):
        if any(op in s for op in ['+', '-', '*', '/', '(', ')', '!']):
            return True
        if len(s) == 1 and s.isalpha():
            return True

    return False


def balance_html_tags(s: str) -> str:
    """Гарантирует, что открытые инлайн-теги корректно закрыты внутри блока и не протекают."""
    tags = ['b', 'i', 'u', 's', 'tg-spoiler', 'a', 'code']
    for tag in tags:
        open_count = len(re.findall(rf'<{tag}\b[^>]*>', s))
        close_count = len(re.findall(rf'</{tag}>', s))
        if open_count > close_count:
            s += f"</{tag}>" * (open_count - close_count)
    return s


def format_inline_markdown(text: str) -> str:
    """Форматирует инлайн Markdown (*, **, __, ~~, ++, ||, [link](url)) с экранированием."""
    if not text:
        return ""

    s = py_html.escape(text, quote=False)

    # 1. Ссылки: [text](url)
    s = re.sub(r'\[([^\]\n]+)\]\((https?://[^\s\)]+)\)', r'<a href="\2">\1</a>', s)

    # 2. Жирный + курсив: ***text***
    s = re.sub(r'\*\*\*([^\n*]+?)\*\*\*', r'<b><i>\1</i></b>', s)

    # 3. Жирный: **text** и __text__
    s = re.sub(r'\*\*([^\n*]+?)\*\*', r'<b>\1</b>', s)
    s = re.sub(r'(?<!\w)__([^\n_]+?)__(?!\w)', r'<b>\1</b>', s)

    # 4. Курсив: *text* и _text_
    s = re.sub(r'(?<!\*)\*([^\n*]+?)\*(?!\*)', r'<i>\1</i>', s)
    s = re.sub(r'(?<![a-zA-Z0-9_])_([^\n_]+?)_(?![a-zA-Z0-9_])', r'<i>\1</i>', s)

    # 5. Зачеркнутый: ~~text~~
    s = re.sub(r'~~([^\n~]+?)~~', r'<s>\1</s>', s)

    # 6. Подчеркнутый: ++text++
    s = re.sub(r'\+\+([^\n\+]+?)\+\+', r'<u>\1</u>', s)

    # 7. Спойлер: ||text||
    s = re.sub(r'\|\|([^\n\|]+?)\|\|', r'<tg-spoiler>\1</tg-spoiler>', s)

    return balance_html_tags(s)


def _render_table(lines: List[str]) -> str:
    """Рендерит Markdown pipe-таблицу в Rich HTML <table bordered="true" striped="true">."""
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


def _render_nested_list_html(lines: List[str]) -> str:
    """
    Превращает строки списка в валидный HTML <ul>/<ol> с поддержкой любой вложенности.
    Поддерживает встроенные инлайн-формулы и форматирование внутри пунктов.
    """
    raw_items = []
    for line in lines:
        ul_m = re.match(r'^([ \t]*)[-*+]\s+(.+)$', line)
        ol_m = re.match(r'^([ \t]*)(\d+)\.\s+(.+)$', line)
        if ul_m:
            indent = len(ul_m.group(1).replace('\t', '    '))
            raw_items.append({'indent': indent, 'type': 'ul', 'content': ul_m.group(2).strip()})
        elif ol_m:
            indent = len(ol_m.group(1).replace('\t', '    '))
            raw_items.append({'indent': indent, 'type': 'ol', 'content': ol_m.group(3).strip()})
        else:
            if raw_items:
                raw_items[-1]['content'] += "<br>" + line.strip()

    if not raw_items:
        return ""

    out = []
    stack: List[Tuple[str, int]] = []

    for item in raw_items:
        indent = item['indent']
        tag = item['type']
        content = format_inline_markdown(item['content'])

        if not stack:
            out.append(f"<{tag}>")
            stack.append((tag, indent))
            out.append(f"  <li>{content}")
        elif indent > stack[-1][1]:
            out.append(f"  <{tag}>")
            stack.append((tag, indent))
            out.append(f"    <li>{content}")
        elif indent == stack[-1][1]:
            out[-1] += "</li>"
            if tag != stack[-1][0]:
                out.append(f"</{stack[-1][0]}>")
                out.append(f"<{tag}>")
                stack[-1] = (tag, indent)
            indent_str = "  " * len(stack)
            out.append(f"{indent_str}<li>{content}")
        else:
            out[-1] += "</li>"
            while len(stack) > 1 and indent < stack[-1][1]:
                closed_tag, _ = stack.pop()
                indent_str = "  " * len(stack)
                out.append(f"{indent_str}</{closed_tag}></li>")

            indent_str = "  " * len(stack)
            out.append(f"{indent_str}<li>{content}")

    out[-1] += "</li>"
    while stack:
        closed_tag, _ = stack.pop()
        indent_str = "  " * len(stack)
        if stack:
            out.append(f"{indent_str}</{closed_tag}></li>")
        else:
            out.append(f"</{closed_tag}>")

    return "\n".join(out)


def _parse_and_extract_lists(text: str, save_block_fn) -> str:
    """Находит блоки списков в тексте и преобразует их в блочные плейсхолдеры."""
    lines = text.split("\n")
    new_lines = []
    i = 0

    while i < len(lines):
        line = lines[i]
        ul_m = re.match(r'^([ \t]*)[-*+]\s+(.+)$', line)
        ol_m = re.match(r'^([ \t]*)(\d+)\.\s+(.+)$', line)

        if ul_m or ol_m:
            list_lines = []
            while i < len(lines):
                curr = lines[i]
                if re.match(r'^[ \t]*[-*+]\s+', curr) or re.match(r'^[ \t]*\d+\.\s+', curr):
                    list_lines.append(curr)
                    i += 1
                elif curr.startswith(('  ', '\t')) and curr.strip():
                    list_lines.append(curr)
                    i += 1
                else:
                    break

            rendered_list = _render_nested_list_html(list_lines)
            new_lines.append(f"\n\n{save_block_fn(rendered_list)}\n\n")
        else:
            new_lines.append(line)
            i += 1

    return "\n".join(new_lines)


def markdown_to_rich_html(text: str, streaming: bool = False) -> str:
    """
    Конвертирует Markdown + LaTeX в нативный Telegram Rich HTML (Bot API 10.1+):
    - Блочные формулы $$...$$ и \\[...\\] -> центрированный <tg-math-block>LaTeX</tg-math-block>
    - Строчные формулы $...$ и \\(...\\) -> <tg-math>LaTeX</tg-math>
    - Заголовки (#, ##, ###) -> <h1>, <h2>, <h3>
    - Нумерованные заголовки вида «1. **Заголовок**» -> <b>1. Заголовок</b>
    - Маркированные и нумерованные списки -> <ul>/<ol>/<li> с поддержкой вложенности
    - Обычный текст структурирован по абзацам <p>...</p>
    - Одиночный перенос строки внутри абзаца превращается в <br>
    - Элементы, слипшиеся через «•», автоматически разбиваются на пункты списка
    - Жирный выделяется только там, где задан в исходнике (**...**), без протекания тегов
    - Цены вроде $5 и доллары в коде не ломаются
    - Символы <, >, & безопасно экранируются в тексте и внутри формул
    """
    if not text:
        return ""

    if streaming:
        text = balance_streaming_markdown(text)

    # Нормализация переводов строк и разделение слипшихся списков
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = clean_squished_bullets(text)

    block_placeholders: List[str] = []
    inline_placeholders: List[str] = []

    def save_block(content: str) -> str:
        idx = len(block_placeholders)
        block_placeholders.append(content)
        return f"\x00RICH_BLOCK_{idx}\x00"

    def save_inline(content: str) -> str:
        idx = len(inline_placeholders)
        inline_placeholders.append(content)
        return f"\x00RICH_INLINE_{idx}\x00"

    # 1. Блоки кода (```lang ... ```)
    def replace_code_block(m: re.Match) -> str:
        lang = (m.group(1) or "").strip()
        code_content = m.group(2).strip("\n")
        esc_code = py_html.escape(code_content, quote=False)
        if lang:
            esc_lang = py_html.escape(lang, quote=False)
            rendered = f'<pre><code class="language-{esc_lang}">{esc_code}</code></pre>'
        else:
            rendered = f'<pre><code>{esc_code}</code></pre>'
        return f"\n\n{save_block(rendered)}\n\n"

    text = re.sub(r'```([a-zA-Z0-9_\-\+]*)\n([\s\S]*?)```', replace_code_block, text)

    # 2. Инлайн-код (`...`)
    def replace_inline_code(m: re.Match) -> str:
        esc_code = py_html.escape(m.group(1), quote=False)
        return save_inline(f'<code>{esc_code}</code>')

    text = re.sub(r'`([^`\n]+)`', replace_inline_code, text)

    # 3. Блочные формулы ($$...$$ и \[...\])
    def replace_math_block(m: re.Match) -> str:
        formula = py_html.escape(m.group(1).strip(), quote=False)
        rendered = f"<tg-math-block>{formula}</tg-math-block>"
        return f"\n\n{save_block(rendered)}\n\n"

    text = re.sub(r'\$\$([\s\S]*?)\$\$', replace_math_block, text)
    text = re.sub(r'\\\[([\s\S]*?)\\\]', replace_math_block, text)

    # 4. Инлайн-формулы ($...$ и \(...\))
    def replace_inline_math(m: re.Match) -> str:
        raw = m.group(1).strip()
        if not is_likely_math(raw):
            return m.group(0)
        esc_formula = py_html.escape(raw, quote=False)
        rendered = f"<tg-math>{esc_formula}</tg-math>"
        return save_inline(rendered)

    text = re.sub(r'(?<![\\\$])\$(?!\s)([^\$\n]+?)(?<!\s)(?<!\\)\$', replace_inline_math, text)
    text = re.sub(r'\\\(([\s\S]+?)\\\)', replace_inline_math, text)

    # 5. Markdown таблицы (| col1 | col2 |)
    lines = text.split("\n")
    proc_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]
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
            rendered_table = _render_table(table_lines)
            proc_lines.append(f"\n\n{save_block(rendered_table)}\n\n")
        else:
            proc_lines.append(line)
            i += 1
    text = "\n".join(proc_lines)

    # 6. Заголовки Markdown (# Header)
    def replace_heading(m: re.Match) -> str:
        level = min(len(m.group(1)), 6)
        h_text = format_inline_markdown(m.group(2).strip())
        rendered = f"<h{level}>{h_text}</h{level}>"
        return f"\n\n{save_block(rendered)}\n\n"

    text = re.sub(r'^[ \t]*(#{1,6})\s+(.+)$', replace_heading, text, flags=re.MULTILINE)

    # 7. Нумерованные заголовки вида "1. **Заголовок**" на отдельной строке
    def replace_num_heading(m: re.Match) -> str:
        num = m.group(1)
        content = m.group(2).strip()
        h_text = format_inline_markdown(content)
        rendered = f"<p><b>{num} {h_text}</b></p>"
        return f"\n\n{save_block(rendered)}\n\n"

    text = re.sub(r'^[ \t]*(\d+\.)\s+\*\*([^\*\n]+)\*\*\s*$', replace_num_heading, text, flags=re.MULTILINE)
    text = re.sub(
        r'^[ \t]*\*\*(\d+\.\s+[^\*\n]+)\*\*\s*$',
        lambda m: f"\n\n{save_block(f'<p><b>{format_inline_markdown(m.group(1).strip())}</b></p>')}\n\n",
        text,
        flags=re.MULTILINE
    )

    # 8. Цитаты (> Quote)
    def replace_quote(m: re.Match) -> str:
        raw_lines = [l.lstrip('>').strip() for l in m.group(0).split('\n') if l.strip()]
        q_content = "<br>".join(format_inline_markdown(l) for l in raw_lines)
        rendered = f"<blockquote>{q_content}</blockquote>"
        return f"\n\n{save_block(rendered)}\n\n"

    text = re.sub(r'^(?:[ \t]*>.*(?:\n|$))+', replace_quote, text, flags=re.MULTILINE)

    # 9. Списки (включая вложенные)
    text = _parse_and_extract_lists(text, save_block)

    # 10. Формирование абзацев <p> и переносов строк <br>
    parts = re.split(r'(\x00RICH_BLOCK_\d+\x00)', text)
    result_blocks = []

    for part in parts:
        if not part:
            continue
        if part.startswith('\x00RICH_BLOCK_') and part.endswith('\x00'):
            result_blocks.append(part)
        else:
            paragraphs = re.split(r'\n\s*\n', part)
            for para in paragraphs:
                para = para.strip()
                if not para:
                    continue
                lines = [l.strip() for l in para.split('\n') if l.strip()]
                if not lines:
                    continue
                formatted_lines = [format_inline_markdown(l) for l in lines]
                para_html = "<br>".join(formatted_lines)
                result_blocks.append(f"<p>{para_html}</p>")

    final_html = "\n\n".join(result_blocks)

    # 11. Восстановление блочных плейсхолдеров
    for idx, repl in enumerate(block_placeholders):
        final_html = final_html.replace(f"\x00RICH_BLOCK_{idx}\x00", repl)

    # 12. Восстановление инлайн-плейсхолдеров
    for idx, repl in enumerate(inline_placeholders):
        final_html = final_html.replace(f"\x00RICH_INLINE_{idx}\x00", repl)

    final_html = re.sub(r'<p>\s*</p>', '', final_html)
    final_html = re.sub(r'\n{3,}', '\n\n', final_html).strip()
    return final_html


def split_rich_message(html_text: str, max_limit: int = 32000) -> List[str]:
    """
    Разбивает Rich HTML сообщение при превышении лимита 32 768 символов.
    Разбивает строго по границам абзацев и никогда посреди формулы или тегов.
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
