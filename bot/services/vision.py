import io
import base64
import logging
from typing import Optional, List, Dict
from PIL import Image
from openai import AsyncOpenAI

from bot.config import settings

logger = logging.getLogger(__name__)

VISION_SYSTEM_PROMPT = """Ты — интеллектуальный визуальный эксперт и универсальный персональный помощник.
Тебя зовут Пётр.
Ты анализируешь изображения (автозапчасти, инструмент, чеки, показания приборов/одометра, маркировки, схемы, документы, товары и любые бытовые предметы).

ПРАВИЛА ОТВЕТА:
1. Отвечай на русском языке, четко, информативно и по делу.
2. Выделяй ключевые термины, названия, артикулы, суммы и показатели жирным шрифтом (**жирный текст**).
3. Если на фото есть текст, маркировка деталей, артикулы или цифры — обязательно распознай и укажи их.
4. Если пользователь задал конкретный вопрос к фотографии в подписи — ответь именно на него.
5. Если подписи нет — подробно опиши, что изображено, дай экспертный комментарий и при необходимости полезный совет.
6. Для формул и расчетов используй понятные символы Unicode (², ³, √, ±, ≈, °, ·, −), без сырого кода LaTeX.
"""


def get_groq_client() -> AsyncOpenAI:
    """Создает экземпляр AsyncOpenAI клиента для Groq API."""
    return AsyncOpenAI(
        base_url="https://api.groq.com/openai/v1",
        api_key=settings.GROQ_API_KEY
    )


def prepare_image_data_uri(image_bytes: bytes, max_dimension: int = 1500) -> str:
    """
    Оптимизирует изображение через Pillow (приведение к RGB, ресайз при превышении max_dimension)
    и кодирует в data:image/jpeg;base64.
    """
    with Image.open(io.BytesIO(image_bytes)) as img:
        # Конвертация в RGB (на случай RGBA, P или CMYK)
        if img.mode != "RGB":
            img = img.convert("RGB")

        # Ресайз с сохранением пропорций, если изображение очень большое
        w, h = img.size
        if max(w, h) > max_dimension:
            scale = max_dimension / max(w, h)
            new_w = max(32, int(w * scale))
            new_h = max(32, int(h * scale))
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

        # Гарантируем минимальный размер для Groq (не менее 32 пикселей)
        if img.width < 32 or img.height < 32:
            img = img.resize((max(32, img.width), max(32, img.height)), Image.Resampling.NEAREST)

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=88, optimize=True)
        b64_str = base64.b64encode(buf.getvalue()).decode("utf-8")
        return f"data:image/jpeg;base64,{b64_str}"


async def analyze_image(
    image_bytes: bytes,
    caption: Optional[str] = None,
    history: Optional[List[Dict[str, str]]] = None
) -> str:
    """
    Анализирует фотографию через модель компьютерного зрения (Groq Qwen Vision).
    Поддерживает контекст предыдущего диалога и пользовательскую подпись к фото.
    """
    data_uri = prepare_image_data_uri(image_bytes)

    # Формирование запроса к модели
    text_prompt = caption.strip() if caption and caption.strip() else (
        "Внимательно изучи эту фотографию. Опиши, что на ней изображено. "
        "Если на ней есть текст, маркировка, артикулы, числа, чеки или показатели приборов — точно распознай их. "
        "Дай экспертную оценку или полезный совет."
    )

    messages = [{"role": "system", "content": VISION_SYSTEM_PROMPT}]

    # Добавляем историю предыдущего общения, если есть
    if history:
        for item in history:
            role = item.get("role")
            content = item.get("content", "").strip()
            if role in ["user", "assistant"] and content:
                messages.append({"role": role, "content": content})

    # Сообщение пользователя с картинкой
    messages.append({
        "role": "user",
        "content": [
            {"type": "text", "text": text_prompt},
            {"type": "image_url", "image_url": {"url": data_uri}}
        ]
    })

    client = get_groq_client()
    candidate_vision_models = ["qwen/qwen3.8-27b"]

    for model_name in candidate_vision_models:
        try:
            logger.info(f"Отправка фото в модель зрения: {model_name}")
            response = await client.chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=0.3,
                max_tokens=2048
            )
            content = response.choices[0].message.content or ""
            if content.strip():
                return content.strip()
        except Exception as e:
            logger.warning(f"Ошибка модели зрения {model_name}: {e}. Пробуем альтернативы...")
            continue

    return "Не удалось проанализировать изображение через модель компьютерного зрения. Попробуйте отправить другое фото или ракурс."
