import json
import logging
from typing import Dict, Any, Optional
from openai import AsyncOpenAI
from bot.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Ты — интеллектуальный персональный ассистент водителя и владельца гаража/дачи, удобный задачник, а также универсальный умный помощник и консультант на все случаи жизни.
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

4. "item_find" — вопрос пользователя о том, где находится вещь/инструмент в гараже/доме (например: "где лежит домкрат?", "где ключи на 13?").
   Поля в "data":
   - "search_query": string (название предмета для поиска)

5. "task_save" — задача, напоминание, список дел, список покупок, любые бытовые и гаражные дела (например: "запиши мне на завтра съездить на дачу купить грабли", "напомни купить омывайку", "надо поменять резину в субботу", "запиши задачу: заехать в сервис").
   Поля в "data":
   - "title": string (суть задачи или покупки, сформулированная четко и понятно)
   - "due_date": string или null (когда нужно сделать: "завтра", "сегодня", "в субботу", "25 сентября" и т.п., либо null если не указано)

6. "task_list" — запрос на просмотр текущих задач, дел, списка покупок или напоминаний (например: "какие у меня дела", "что записано", "покажи список задач", "что нужно сделать", "что купить").
   Поля в "data": {}

7. "ask_assistant" — любой общий вопрос, консультация, совет (по автомобилю, технике, кулинарии, здоровью, быту, законам, ремонту), просьба найти информацию в интернете или обычное общение ("привет", "как дела", "сколько варить яйца", "какой штраф за превышение на 20 км/ч", "какая погода в Москве", "найди в интернете курс доллара", "сколько стоит iPhone").
   Поля в "data":
   - "needs_web_search": boolean (СТАВЬ true, ТОЛЬКО ЕСЛИ требуются свежие/актуальные данные из интернета: погода, текущий курс валют, свежие новости, актуальные цены, расписание, спортивные результаты или пользователь прямо просит: "найди в интернете", "погугли", "поищи". Для общих знаний, советов, автомеханики, рецептов, расчетов, общения — СТАВЬ false).
   - "search_query": string или null (короткий эффективный поисковый запрос для поисковика, если needs_web_search=true; иначе null).
   - "user_query": string (суть вопроса пользователя).

8. "unknown" — только случайный несвязный шум микрофона или неразборчивые звуки.

ВАЖНЫЕ ПРАВИЛА:
- Будь максимально гибок к разговорной речи, сленгу и естественным формулировкам.
- Если человек говорит "надо съездить...", "купить...", "запиши мне...", "напомни..." — это ВСЕГДА "task_save"!
- Если вопрос не касается записи дел и расходов, а является вопросом/просьбой подсказать — это "ask_assistant".
- Ответ должен быть СТРОГО валидным JSON-объектом без лишнего текста и markdown-оберток.

Формат JSON:
{
  "intent": "fuel" | "service" | "item_save" | "item_find" | "task_save" | "task_list" | "ask_assistant" | "unknown",
  "data": { ... }
}
"""


def get_groq_client() -> AsyncOpenAI:
    """Создает экземпляр AsyncOpenAI клиента для Groq API."""
    return AsyncOpenAI(
        base_url="https://api.groq.com/openai/v1",
        api_key=settings.GROQ_API_KEY
    )


async def parse_user_intent(text: str, context: Optional[str] = None) -> Dict[str, Any]:
    """
    Парсит текст пользователя через Groq LLM в строгий JSON.
    Принимает опциональный контекст последних реплик для точного разрешения местоимений
    ("а для 50?", "почему так?", "запиши это").
    Использует qwen/qwen3.8-27b с автоматическим fallback на gpt-oss-120b.
    """
    client = get_groq_client()

    candidate_models = [settings.GROQ_MODEL]
    for fallback in ["qwen/qwen3.8-27b", "openai/gpt-oss-120b", "openai/gpt-oss-20b", "groq/compound-mini"]:
        if fallback not in candidate_models:
            candidate_models.append(fallback)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if context:
        messages.append({
            "role": "system",
            "content": f"Контекст последних сообщений диалога с пользователем:\n{context}"
        })
    messages.append({"role": "user", "content": text})

    for model_name in candidate_models:
        try:
            response = await client.chat.completions.create(
                model=model_name,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.1
            )

            content = response.choices[0].message.content or "{}"
            parsed = json.loads(content)

            if "intent" in parsed and "data" in parsed:
                logger.info(f"Успешный парсинг интента моделью {model_name}: {parsed.get('intent')}")
                return parsed

        except json.JSONDecodeError as e:
            logger.warning(f"Ошибка JSONDecode от модели {model_name}: {e}")
            continue
        except Exception as e:
            logger.warning(f"Модель {model_name} вернула ошибку: {e}. Пробуем следующую модель...")
            continue

    logger.error("Все доступные модели Groq не смогли разобрать сообщение")
    return {"intent": "unknown", "data": {}}
