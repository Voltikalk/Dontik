import json
import logging
from typing import Dict, Any
from openai import AsyncOpenAI
from bot.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Ты — интеллектуальный персональный ассистент водителя и владельца гаража/дачи, а также удобный задачник и ежедневник.
Твоя задача — распарсить свободную русскую речь пользователя в строгий JSON.

Возможные значения "intent":
1. "fuel" — заправка автомобиля.
   Поля в "data":
   - "liters": float (литры)
   - "cost": float (стоимость в рублях)
   - "odometer": int (пробег на одометре в км)
   - "station": string или null (название АЗС, например Лукойл, Роснефть, Газпромнефть)

2. "service" — техническое обслуживание, ремонт автомобиля, мойка или покупка автозапчастей.
   Поля в "data":
   - "title": string (что было сделано, например: замена масла, колодки, шиномонтаж)
   - "cost": float или null (стоимость работ/запчастей)
   - "odometer": int или null (пробег в км)
   - "notes": string или null (заметки, бренд масла, артикул и т.д.)

3. "item_save" — запомнить, куда положена вещь/инструмент/деталь в гараже или на даче (например: "положил дрель на верхнюю полку").
   Поля в "data":
   - "item_name": string (название вещи или инструмента)
   - "location": string (место, где лежит вещь)

4. "item_find" — вопрос пользователя о том, где находится вещь/инструмент (например: "где лежит домкрат?").
   Поля в "data":
   - "search_query": string (название предмета для поиска)

5. "task_save" — задача, напоминание, список дел, список покупок, любые бытовые и гаражные дела (например: "запиши мне на завтра съездить на дачу купить грабли", "напомни купить омывайку", "надо поменять резину в субботу", "запиши задачу: заехать в сервис").
   Поля в "data":
   - "title": string (суть задачи или покупки, сформулированная четко и понятно)
   - "due_date": string или null (когда нужно сделать: "завтра", "сегодня", "в субботу", "25 сентября" и т.п., либо null если не указано)

6. "task_list" — запрос на просмотр текущих задач, дел, списка покупок или напоминаний (например: "какие у меня дела", "что записано", "покажи список задач", "что нужно сделать", "что купить").
   Поля в "data": {}

7. "unknown" — если сообщение не несет никакого смысла или является простым приветствием/шуткой.
   Поля в "data": {}

ВАЖНЫЕ ПРАВИЛА:
- Будь максимально гибок к разговорной речи, сленгу и естественным формулировкам. Если человек говорит "надо съездить...", "купить...", "запиши мне...", "напомни..." — это ВСЕГДА "task_save"!
- Если какой-либо параметр не назван пользователем, выставляй null (не выдумывай значения).
- Ответ должен быть СТРОГО валидным JSON-объектом без лишнего текста и markdown-оберток.

Формат JSON:
{
  "intent": "fuel" | "service" | "item_save" | "item_find" | "task_save" | "task_list" | "unknown",
  "data": { ... }
}
"""


def get_groq_client() -> AsyncOpenAI:
    """Создает экземпляр AsyncOpenAI клиента для Groq API."""
    return AsyncOpenAI(
        base_url="https://api.groq.com/openai/v1",
        api_key=settings.GROQ_API_KEY
    )


async def parse_user_intent(text: str) -> Dict[str, Any]:
    """
    Парсит текст пользователя через модель llama-3.3-70b-versatile в строгий JSON.
    
    Возвращает словарь формата:
    {
        "intent": "fuel" | "service" | "item_save" | "item_find" | "unknown",
        "data": { ... }
    }
    """
    client = get_groq_client()

    try:
        response = await client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text}
            ],
            response_format={"type": "json_object"},
            temperature=0.1
        )

        content = response.choices[0].message.content or "{}"
        parsed = json.loads(content)

        # Валидация базовой структуры
        if "intent" not in parsed or "data" not in parsed:
            return {"intent": "unknown", "data": {}}

        return parsed

    except json.JSONDecodeError as e:
        logger.error(f"Ошибка декодирования JSON от Groq LLM: {e}")
        return {"intent": "unknown", "data": {}}
    except Exception as e:
        logger.error(f"Ошибка при вызове Groq LLM: {e}", exc_info=True)
        return {"intent": "unknown", "data": {}}
