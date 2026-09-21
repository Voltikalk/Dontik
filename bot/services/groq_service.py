import json
import logging
from typing import Dict, Any, Optional
from openai import AsyncOpenAI

from bot.config import settings

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """Ты — интеллектуальный ассистент водителя и владельца гаража «Авто-Гараж Ассистент».
Твоя задача — проанализировать сообщение пользователя (текстовое или распознанный голос) и извлечь намерение и параметры в строгом JSON-формате.

Возможные намерения (поле "intent"):
1. "fuel_log" — добавление информации о заправке автомобиля.
   Поля в "data":
   - "liters": float (объем топлива в литрах)
   - "cost": float (общая стоимость в рублях)
   - "odometer": int (текущий пробег автомобиля в км, 0 если не указан)
   - "station_name": string или null (название АЗС: Лукойл, Газпромнефть, Роснефть и т.д.)

2. "service_log" — добавление информации о техническом обслуживании, ремонте, мойке или покупке запчастей.
   Поля в "data":
   - "title": string (краткое описание: замена масла, колодки, шиномонтаж и т.д.)
   - "cost": float или null (стоимость работ/деталей)
   - "odometer": int (пробег на момент работ, 0 если не указан)
   - "notes": string или null (дополнительные заметки, бренд масла, артикул и т.д.)

3. "set_location" — запомнить, куда положена вещь/инструмент/запчасть в гараже или на даче.
   Поля в "data":
   - "item_name": string (название вещи, инструмента или детали)
   - "location": string (где именно лежит, например: "на 2 полке слева", "в багажнике", "в синем ящике")

4. "find_location" — вопрос пользователя о том, где лежит та или иная вещь.
   Поля в "data":
   - "item_name": string (что ищет пользователь)

5. "show_stats" — запрос статистики или истории (заправки, расходы, список вещей).
   Поля в "data":
   - "category": string ("fuel", "service", "items" или "all")

6. "general_query" — вопрос по автомобильной тематике, совет по ремонту или обычный диалог.
   Поля в "data":
   - "reply": string (твой краткий, полезный и вежливый ответ водителю)

Формат ответа СТРОГО JSON:
{
  "intent": "fuel_log" | "service_log" | "set_location" | "find_location" | "show_stats" | "general_query",
  "confidence": float (от 0.0 до 1.0),
  "data": { ... }
}
"""


class GroqService:
    """Сервис для интеграции с Groq API (Whisper + Llama)."""

    def __init__(self):
        self._client: Optional[AsyncOpenAI] = None

    @property
    def client(self) -> AsyncOpenAI:
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=settings.GROQ_API_KEY,
                base_url="https://api.groq.com/openai/v1",
                max_retries=0
            )
        return self._client

    async def transcribe_audio(self, file_bytes: bytes, filename: str = "voice.ogg") -> str:
        """
        Распознает речь из аудиофайла с помощью Groq Whisper.
        """
        try:
            transcription = await self.client.audio.transcriptions.create(
                model=settings.GROQ_WHISPER_MODEL,
                file=(filename, file_bytes, "audio/ogg"),
                language="ru",
                response_format="text"
            )
            return transcription.strip() if isinstance(transcription, str) else str(transcription).strip()
        except Exception as e:
            logger.error(f"Ошибка транскрибации Groq Whisper: {e}", exc_info=True)
            raise

    async def parse_intent_and_data(self, text: str) -> Dict[str, Any]:
        """
        Извлекает намерение пользователя и структурированные данные через LLM в JSON.
        """
        try:
            response = await self.client.chat.completions.create(
                model=settings.GROQ_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": text}
                ],
                response_format={"type": "json_object"},
                temperature=0.1
            )
            raw_content = response.choices[0].message.content or "{}"
            parsed = json.loads(raw_content)
            return parsed
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка декодирования JSON ответа LLM: {e}. Сырой ответ: {raw_content}")
            return {
                "intent": "general_query",
                "confidence": 0.5,
                "data": {"reply": "Не удалось корректно разобрать данные. Пожалуйста, повторите запрос."}
            }
        except Exception as e:
            logger.error(f"Ошибка вызова Groq LLM: {e}", exc_info=True)
            raise


groq_service = GroqService()
