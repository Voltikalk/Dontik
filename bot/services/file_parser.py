import os
import csv
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

MAX_CHARS_LIMIT = 25000  # Максимальное количество символов из одного документа для LLM


import io
import pymupdf
from PIL import Image

def is_text_meaningful(text: str) -> bool:
    """
    Проверяет, является ли извлеченный текст осмысленным и читаемым человеком,
    а не набором битых шрифтов, кракозябр или спецсимволов.
    """
    clean_text = text.strip()
    if len(clean_text) < 30:
        return False

    alpha_chars = sum(1 for c in clean_text if c.isalpha())
    total_chars = len(clean_text)

    # Доля букв (латиница или кириллица) должна быть не менее 45%
    if (alpha_chars / total_chars) < 0.45:
        return False

    # Проверяем наличие гласных букв
    vowels = set("аеёиоуыэюяaeiouyАЕЁИОУЫЭЮЯAEIOUY")
    vowel_count = sum(1 for c in clean_text if c in vowels)
    if (vowel_count / max(1, alpha_chars)) < 0.15:
        return False

    return True


def render_pdf_to_image_bytes(doc: pymupdf.Document, max_pages: int = 3, dpi: int = 160) -> bytes:
    """
    Рендерит первые max_pages страниц PDF в одно объединенное JPEG изображение
    для последующего оптического анализа (Vision OCR).
    """
    images = []
    num_pages = min(len(doc), max_pages)
    for i in range(num_pages):
        page = doc[i]
        pix = page.get_pixmap(dpi=dpi)
        img = Image.open(io.BytesIO(pix.tobytes("jpeg")))
        images.append(img)

    if not images:
        return b""

    if len(images) == 1:
        buf = io.BytesIO()
        images[0].save(buf, format="JPEG", quality=90)
        return buf.getvalue()

    # Склеиваем страницы вертикально
    total_height = sum(img.height for img in images)
    max_width = max(img.width for img in images)
    combined = Image.new("RGB", (max_width, total_height), color="white")
    y_offset = 0
    for img in images:
        combined.paste(img, (0, y_offset))
        y_offset += img.height

    buf = io.BytesIO()
    combined.save(buf, format="JPEG", quality=88)
    return buf.getvalue()


def parse_pdf_smart(file_path: str, max_chars: int = MAX_CHARS_LIMIT):
    """
    Интеллектуальный разбор PDF:
    - Извлекает текстовый слой через PyMuPDF.
    - Если текст осмысленный и подробный -> возвращает ('text', text, None).
    - Если документ является сканом, сертификатом, чеком или текст поврежден/кракозябры ->
      рендерит страницы в высококачественное изображение для компьютерного зрения ('image', None, image_bytes).
    """
    try:
        doc = pymupdf.open(file_path)
        total_pages = len(doc)
        extracted_text = []
        current_len = 0

        for idx, page in enumerate(doc, 1):
            page_text = (page.get_text("text") or "").strip()
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

        full_text = "\n".join(extracted_text).strip()

        # Если текста мало или он битый (кракозябры, нераспознанный шрифт, сертификат-картинка)
        # переключаемся на Vision рендеринг страниц
        is_sparse_or_short = (total_pages <= 2 and len(full_text) < 120)
        if not is_text_meaningful(full_text) or is_sparse_or_short:
            logger.info(f"PDF {file_path} распознан как визуальный документ (скан/сертификат/кракозябры). Рендерим страницы в изображение...")
            img_bytes = render_pdf_to_image_bytes(doc, max_pages=3, dpi=160)
            if img_bytes:
                return "image", None, img_bytes

        if full_text:
            return "text", full_text, None

    except Exception as e:
        logger.warning(f"Ошибка в pymupdf при анализе {file_path}: {e}. Пробуем запасной вариант...")

    # Запасной вариант через pypdf
    try:
        import pypdf
        reader = pypdf.PdfReader(file_path)
        extracted = []
        for p in reader.pages:
            t = p.extract_text()
            if t:
                extracted.append(t)
        pypdf_text = "\n".join(extracted).strip()
        if is_text_meaningful(pypdf_text):
            return "text", pypdf_text, None
    except Exception:
        pass

    return "text", "В PDF-документе не удалось найти печатный текст или отрендерить страницы.", None


def parse_pdf(file_path: str, max_chars: int = MAX_CHARS_LIMIT) -> str:
    """Для обратной совместимости извлечения текста."""
    kind, text, _ = parse_pdf_smart(file_path, max_chars)
    return text or "Документ не содержит читаемого текста."


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
