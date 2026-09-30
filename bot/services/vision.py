"""Анализ изображений через мультимодальную модель Groq."""

import base64
import io
import logging
from typing import Optional

from PIL import Image

from bot.services.llm import chat_completion

logger = logging.getLogger(__name__)

VISION_SYSTEM_PROMPT = """Ты — «Пётр», визуальный эксперт и повседневный помощник.
Ты анализизируешь изображения: автозапчасти, инструмент, чеки, приборные панели и одометр,
маркировки и артикулы, схемы и чертежи, документы, товары и бытовые предметы.

ПРАВИЛА ОТВЕТА:
1. Отвечай на русском, по делу, без воды.
2. Ключевые термины, артикулы, суммы и показания выделяй жирным: **так**.
3. Весь читаемый текст на фото распознавай точно: цифры, маркировку, надписи.
4. Если в подписи есть конкретный вопрос — отвечай именно на него.
5. Если подписи нет — опиши, что изображено, и дай полезный экспертный комментарий.
6. Формулы и расчёты — в LaTeX блоками $$...$$, короткие обозначения — в $...$.
   Допустимые команды: \\frac{}{}, \\sqrt{}, \\cdot, \\approx, \\pm, \\times.
   НЕ используй \\boxed и \\begin{align}.
7. Если на фото плохо видно или это не то, что можно распознать — честно скажи об этом,
   не выдумывай артикулы и цифры.
"""

# Модели с поддержкой изображений, от самой сильной к быстрой.
VISION_MODELS = [
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "qwen/qwen3.8-27b",
]

MAX_DIMENSION = 1500


def prepare_image_data_uri(image_bytes: bytes, max_dimension: int = MAX_DIMENSION) -> str:
    """
    Приводит изображение к RGB, уменьшает до max_dimension по большей стороне
    и кодирует в data:image/jpeg;base64 для API.
    """
    with Image.open(io.BytesIO(image_bytes)) as img:
        if img.mode != "RGB":
            img = img.convert("RGB")

        w, h = img.size
        if max(w, h) > max_dimension:
            scale = max_dimension / max(w, h)
            img = img.resize(
                (max(32, int(w * scale)), max(32, int(h * scale))),
                Image.Resampling.LANCZOS,
            )

        if img.width < 32 or img.height < 32:
            img = img.resize(
                (max(32, img.width), max(32, img.height)),
                Image.Resampling.NEAREST,
            )

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=88, optimize=True)
        return f"data:image/jpeg;base64,{base64.b64encode(buf.getvalue()).decode('utf-8')}"


async def analyze_image(
    image_bytes: bytes,
    caption: Optional[str] = None,
    history: Optional[list[dict]] = None,
) -> str:
    """
    Анализирует изображение мультимодальной моделью Groq.
    Поддерживает подпись пользователя и контекст предыдущих реплик диалога.
    """
    try:
        data_uri = prepare_image_data_uri(image_bytes)
    except Exception as exc:  # noqa: BLE001
        logger.error("Не удалось подготовить изображение: %s", exc)
        return (
            "Не получилось прочитать изображение — файл повреждён или формат не поддерживается. "
            "Пришли фото ещё раз или опиши вопрос текстом."
        )

    text_prompt = (caption or "").strip() or (
        "Внимательно изучи фотографию. Опиши, что на ней изображено. "
        "Если есть текст, маркировка, артикулы, числа или показания приборов — распознай их точно. "
        "Дай экспертную оценку и полезный совет."
    )

    messages: list[dict] = [{"role": "system", "content": VISION_SYSTEM_PROMPT}]

    for item in history or []:
        role = item.get("role")
        content = (item.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content[:600]})

    messages.append({
        "role": "user",
        "content": [
            {"type": "text", "text": text_prompt},
            {"type": "image_url", "image_url": {"url": data_uri}},
        ],
    })

    try:
        return await chat_completion(
            messages,
            preferred_model=VISION_MODELS[0],
            temperature=0.3,
            max_tokens=1800,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Модель зрения не справилась: %s", exc)
        return (
            "Не удалось проанализировать изображение: модель зрения сейчас недоступна. "
            "Попробуй ещё раз через минуту или опиши вопрос текстом."
        )