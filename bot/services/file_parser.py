import os
import csv
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

MAX_CHARS_LIMIT = 25000  # Максимальное количество символов из одного документа для LLM


def parse_pdf(file_path: str, max_chars: int = MAX_CHARS_LIMIT) -> str:
    """Извлекает текст из PDF документа с разбивкой по страницам."""
    import pypdf

    reader = pypdf.PdfReader(file_path)
    total_pages = len(reader.pages)
    extracted_text = []
    current_len = 0

    for idx, page in enumerate(reader.pages, 1):
        page_text = page.extract_text() or ""
        page_text = page_text.strip()
        if not page_text:
            continue

        header = f"\n--- [Страница {idx} из {total_pages}] ---\n"
        if current_len + len(header) + len(page_text) > max_chars:
            extracted_text.append(header)
            remaining = max_chars - current_len - len(header)
            if remaining > 50:
                extracted_text.append(page_text[:remaining] + "\n... [текст документа далее усечен по лимиту объема]")
            break

        extracted_text.append(header + page_text)
        current_len += len(header) + len(page_text)

    if not extracted_text:
        return "В PDF-документе не удалось найти печатный текст (возможно, документ состоит из сканов/изображений без OCR)."

    return "\n".join(extracted_text)


def parse_docx(file_path: str, max_chars: int = MAX_CHARS_LIMIT) -> str:
    """Извлекает текст, заголовки и таблицы из документа Microsoft Word (.docx)."""
    import docx

    doc = docx.Document(file_path)
    lines = []
    current_len = 0

    # 1. Извлекаем абзацы
    for p in doc.paragraphs:
        txt = p.text.strip()
        if txt:
            lines.append(txt)
            current_len += len(txt) + 1
            if current_len >= max_chars:
                lines.append("... [текст документа усечен по лимиту объема]")
                return "\n".join(lines)

    # 2. Извлекаем таблицы
    if doc.tables:
        lines.append("\n--- [Таблицы в документе] ---")
        for t_idx, table in enumerate(doc.tables, 1):
            lines.append(f"\nТаблица {t_idx}:")
            for row in table.rows:
                row_vals = [cell.text.strip().replace("\n", " ") for cell in row.cells]
                # Убираем дубликаты объединенных ячеек
                row_str = " | ".join(row_vals)
                lines.append(f"| {row_str} |")
                current_len += len(row_str) + 4
                if current_len >= max_chars:
                    lines.append("... [таблица усечена по лимиту объема]")
                    return "\n".join(lines)

    if not lines:
        return "Документ Word не содержит текста."

    return "\n".join(lines)


def parse_excel(file_path: str, max_chars: int = MAX_CHARS_LIMIT) -> str:
    """Извлекает данные из электронных таблиц Excel (.xlsx, .xlsm)."""
    import openpyxl

    wb = openpyxl.load_workbook(file_path, data_only=True, read_only=True)
    lines = []
    current_len = 0

    for sheet_name in wb.sheetnames:
        sheet = wb[sheet_name]
        lines.append(f"\n--- [Лист Excel: «{sheet_name}»] ---")

        row_count = 0
        for row in sheet.iter_rows(values_only=True):
            # Пропускаем полностью пустые строки
            if not row or not any(v is not None for v in row):
                continue

            row_count += 1
            if row_count > 150:
                lines.append(f"... [Лист «{sheet_name}» содержит более 150 строк, показаны первые 150]")
                break

            vals = [str(v).strip().replace("\n", " ") if v is not None else "" for v in row]
            # Убираем лишние пустые хвосты колонок
            while vals and not vals[-1]:
                vals.pop()

            if vals:
                row_str = " | ".join(vals)
                lines.append(f"| {row_str} |")
                current_len += len(row_str) + 4
                if current_len >= max_chars:
                    lines.append("... [таблица усечена по лимиту объема]")
                    wb.close()
                    return "\n".join(lines)

    wb.close()

    if not lines:
        return "Файл Excel не содержит данных."

    return "\n".join(lines)


def parse_csv(file_path: str, max_chars: int = MAX_CHARS_LIMIT) -> str:
    """Извлекает данные из CSV файлов с автоопределением кодировки (UTF-8 / CP1251)."""
    raw_bytes = Path(file_path).read_bytes()
    text = ""
    for enc in ["utf-8", "cp1251", "utf-8-sig", "latin1"]:
        try:
            text = raw_bytes.decode(enc)
            break
        except UnicodeDecodeError:
            continue

    if not text:
        return "Не удалось декодировать содержимое CSV файла."

    lines = []
    current_len = 0

    # Автоопределение разделителя
    sample = text[:2048]
    delimiter = ";" if sample.count(";") > sample.count(",") else ","

    reader = csv.reader(text.splitlines(), delimiter=delimiter)
    for idx, row in enumerate(reader, 1):
        if idx > 200:
            lines.append("... [CSV содержит более 200 строк, показаны первые 200]")
            break
        if row and any(v.strip() for v in row):
            row_str = " | ".join(v.strip() for v in row)
            lines.append(f"| {row_str} |")
            current_len += len(row_str) + 4
            if current_len >= max_chars:
                lines.append("... [данные усечены по лимиту объема]")
                break

    return "\n".join(lines)


def parse_text_file(file_path: str, max_chars: int = MAX_CHARS_LIMIT) -> str:
    """Считывает текстовые файлы (.txt, .md, .json, .py, .log, .sql и др.)."""
    raw_bytes = Path(file_path).read_bytes()
    for enc in ["utf-8", "cp1251", "utf-8-sig", "latin1"]:
        try:
            text = raw_bytes.decode(enc)
            if len(text) > max_chars:
                return text[:max_chars] + "\n\n... [текст файла усечен по лимиту объема]"
            return text
        except UnicodeDecodeError:
            continue
    return "Не удалось прочитать текстовый файл в поддерживаемых кодировках (UTF-8, CP1251)."


def extract_text_from_file(file_path: str, filename: str) -> str:
    """
    Главная функция извлечения текста из файла любого поддерживаемого формата.
    """
    ext = Path(filename).suffix.lower()
    logger.info(f"Извлечение текста из файла '{filename}' (расширение: {ext})")

    try:
        if ext == ".pdf":
            return parse_pdf(file_path)
        elif ext in [".docx", ".doc"]:
            if ext == ".doc":
                return "Формат .doc устарел. Пожалуйста, сохраните файл в современном формате .docx или PDF."
            return parse_docx(file_path)
        elif ext in [".xlsx", ".xlsm", ".xls"]:
            if ext == ".xls":
                return "Формат .xls устарел. Пожалуйста, сохраните таблицу в современном формате .xlsx или .csv."
            return parse_excel(file_path)
        elif ext == ".csv":
            return parse_csv(file_path)
        elif ext in [".txt", ".md", ".json", ".py", ".log", ".sql", ".xml", ".html", ".css", ".js", ".yaml", ".yml", ".ini", ".cfg", ".sh", ".bat"]:
            return parse_text_file(file_path)
        else:
            return (
                f"Формат файла '{ext}' не поддерживается для прямого текстового анализа.\n"
                "Поддерживаются: PDF (.pdf), Word (.docx), Excel (.xlsx, .csv), а также любые текстовые файлы (.txt, .md, .json, .py, .log)."
            )
    except Exception as e:
        logger.error(f"Ошибка при парсинге файла {filename}: {e}", exc_info=True)
        return f"Произошла ошибка при чтении файла {filename}: {e}"
