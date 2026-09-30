import time
import re
import logging
from typing import Optional, List, Dict, AsyncGenerator
from aiogram.types import Message
from aiogram.exceptions import TelegramBadRequest

from bot.services.web_search import search_web
from bot.emojis import E_SEARCH, E_THINK
from bot.services.llm import chat_completion, chat_completion_stream, build_token_budget
from bot.services.formatters import (
    fix_squished_bullets
)
from bot.services.rich_message import send_rich_response

logger = logging.getLogger(__name__)

ASSISTANT_SYSTEM_PROMPT = r"""Ты — «Пётр», личный помощник водителя, владельца гаража и просто человека, которому нужен толковый совет каждый день. Ты дружелюбный, спокойный и очень въедливый в деталях.

ТВОЯ РОЛЬ: помогать по широкому кругу тем — автомобиль и гараж, ремонт и строительство, кухня и рецепты, здоровье, деньги и бюджет, закон и бытовые вопросы, учёба, наука, математика, технологии, поездки и связь.

═══════════════════════════════════
1. ФОРМАТ ОТВЕТА
═══════════════════════════════════
- Сразу к делу. Никаких вступлений вроде «Конечно!», «Отличный вопрос!», «Давайте разберёмся».
- Разбивай ответ на разделы с заголовками Markdown (`## Заголовок`). Заголовок — до 4 слов.
- Между абзацами, списками и формулами ВСЕГДА пустая строка. Сплошной простыня в один абзац запрещена.
- Списки: `- **Термин** — пояснение`, каждый пункт с новой строки. Не склеивай пункты через «•» в одну строку.
- Жирным выделяй только названия, термины, числа-выводы и метки. Не выделяй жирным целые предложения.
- Таблицы (`|...|`) запрещены: Telegram их ломает. Используй списки.
- Ссылки и источники — одной строкой в самом конце: `🔗 **Источники:** [Название](URL) • [Название](URL)`

═══════════════════════════════════
2. МАТЕМАТИКА, ФИЗИКА, ХИМИЯ — ОБЯЗАТЕЛЬНЫЕ ПРАВИЛА
═══════════════════════════════════
Это приоритет №1. Формулы рендерятся нативно и должны быть безупречны.

- ЛЮБАЯ формула, уравнение, выражение, интеграл, производная, матрица, дробь, корень, степень — ТОЛЬКО в LaTeX.
- Ключевая формула или итоговое уравнение — ОТДЕЛЬНЫМ блоком `$$...$$` на отдельной строке (Telegram центрирует и рисует его нативно).
- Короткая переменная внутри фразы — в строке `$...$` (например: `скорость $v$`, `время $t$`).
- Допустимые команды: `\frac{}{}`, `\sqrt{}`, `\int`, `\sum`, `\prod`, `\lim`, `\partial`, `\nabla`, `\pi`, `\mu`, `\rho`, `\omega`, `\Delta`, `\alpha`…`\omega`, `\sin \cos \tan \log \ln \exp \cdot \times \leq \geq \neq \approx \pm \infty`, `\begin{pmatrix}...\end{pmatrix}`, `\begin{cases}...\end{cases}`, `\left( \right)`.
- ЗАПРЕЩЕНО: `\boxed` (обрезается), `\text{}` внутри формул, `\begin{align}`/`equation` (не поддерживаются), вложенные `$` внутри `$$`.
- ПОСЛЕ каждОГО решения обязательно приводи РЕЗУЛЬТАТ отдельной строкой в блоке `$$...$$`. Никогда не оставляй ответ только в тексте.
- Если условие задачи непонятно или данных не хватает — реши максимум и прямо скажи, чего не хватает. Не выдумывай условия.
- Проверяй арифметику перед выводом. Если сомневаешься в результате — пересчитай и покажи ход решения, а не только ответ.

═══════════════════════════════════
3. ДЛИНА И ТОН
═══════════════════════════════════
- Простые вопросы — коротко (3–6 строк). Не раздувай ради объёма.
- Сложные задачи — пошагово, с заголовками и формулами.
- Обращайся на «ты», по-человечески, без сюсюканья и канцелярита.
- Приоритет: точность > полнота > красота.

═══════════════════════════════════
4. ВЕБ-ПОИСК
═══════════════════════════════════
- Если в системном сообщении дан блок «АКТУАЛЬНЫЕ ДАННЫЕ ИЗ СЕТИ», используй его как фактческую базу и НЕ пересказывай выдачу списком сайтов.
- Не выдумывай URL. Приводи только те ссылки, которые реально есть в блоке данных.
- Если данных из сети не хватило — честно скажи об этом.
"""

WEB_INSTRUCTION = (
    "СТРОГИЕ ИНСТРУКЦИИ ПО ИСПОЛЬЗОВАНИЮ РЕЗУЛЬТАТОВ ПОИСКА:\n"
    "1. Не пересказывай поисковую выдачу списком сайтов. Сформируй единый, структурированный, готовый ответ.\n"
    "2. Никаких markdown-таблиц с символом | — Telegram их ломает. Оформляй списками.\n"
    "3. Не выдумывай ссылки: используй ТОЛЬКО URL из блока данных.\n"
    "4. Формулы, если они есть в задаче, оформляй в LaTeX блоками $$...$$.\n"
    "5. В самом конце, если это уместно, добавь одну строку: '🔗 **Источники:** [Название](URL) • [Название](URL)'."
)


async def _build_messages(
    user_query: str,
    history: Optional[List[Dict[str, str]]],
    needs_web: bool,
    search_query: Optional[str],
) -> List[dict]:
    """Собирает список сообщений для LLM с токен-бюджетом на историю."""
    prompt_content = f"Вопрос пользователя: {user_query}"

    if needs_web:
        effective_query = (search_query or user_query).strip()
        logger.info("Веб-поиск для ассистента: «%s»", effective_query)
        search_results = await search_web(effective_query, max_results=4)

        if search_results:
            snippets = []
            for idx, r in enumerate(search_results, 1):
                snippets.append(f"[{idx}] {r['title']}\n{r['body']}\nИсточник: {r['href']}")
            web_context = (
                "\n\n--- АКТУАЛЬНЫЕ ДАННЫЕ ИЗ СЕТИ ИНТЕРНЕТ ---\n"
                + "\n\n".join(snippets)
                + "\n---\n"
            )
            prompt_content += f"\n{web_context}\n{WEB_INSTRUCTION}"
        else:
            prompt_content += (
                "\n\n(Поиск в интернете не дал результатов. Ответь по своим знаниям "
                "и честно предупреди, что данные могут быть неполными.)"
            )

    messages: List[dict] = [{"role": "system", "content": ASSISTANT_SYSTEM_PROMPT}]

    for item in history or []:
        role = item.get("role")
        content = (item.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": prompt_content})
    return build_token_budget(messages)


async def answer_query(
    user_query: str,
    needs_web: bool = False,
    search_query: Optional[str] = None,
    history: Optional[List[Dict[str, str]]] = None
) -> str:
    """
    Генерирует ответ ассистента на произвольный вопрос пользователя.
    Поддерживает контекст предыдущих реплик диалога и веб-поиск через DuckDuckGo.
    """
    messages = await _build_messages(user_query, history, needs_web, search_query)
    try:
        return await chat_completion(
            messages,
            temperature=0.3,
            max_tokens=1800,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Ассистент не смог ответить: %s", exc)
        return (
            "Не удалось получить ответ от нейросети прямо сейчас. "
            "Попробуй переформулировать вопрос или повторить через минуту."
        )


async def stream_query_answer(
    user_query: str,
    needs_web: bool = False,
    search_query: Optional[str] = None,
    history: Optional[List[Dict[str, str]]] = None
) -> AsyncGenerator[str, None]:
    """Потоковый ответ ассистента по токенам (stream=True)."""
    messages = await _build_messages(user_query, history, needs_web, search_query)

    try:
        async for delta in chat_completion_stream(
            messages,
            temperature=0.3,
            max_tokens=1800,
        ):
            yield delta
        return
    except Exception as exc:  # noqa: BLE001
        logger.warning("Стриминг не удался (%s), пробуем обычный запрос", exc)

    fallback = await answer_query(
        user_query=user_query,
        needs_web=False,  # поиск уже выполнен выше, повторять не нужно
        search_query=search_query,
        history=history,
    )
    if fallback:
        yield fallback


def clean_for_preview(text: str) -> str:
    """Очищает промежуточный текст для аккуратного отображения курсора при живом наборе."""
    s = fix_squished_bullets(text)
    s = re.sub(r'</?(?:tg-math|tg-math-block)[^>]*?>?', '', s)
    s = re.sub(r'</?(?:b|i|u|s|code|pre|blockquote|a|tg-emoji)[^>]*?>?', '', s)
    s = s.replace(r'\int', '∫').replace(r'\sum', '∑').replace(r'\infty', '∞')
    s = re.sub(r'\\(?:sin|cos|tan|ln|log|exp|sqrt|pi)\b', lambda m: m.group(0)[1:], s)
    s = re.sub(r'\\frac\{([^}]+)\}\{([^}]+)\}', r'\1/\2', s)
    s = s.replace('$$', ' ').replace('$', '')
    s = re.sub(r'[{}]', '', s)
    return s.strip()


async def stream_assistant_response(
    message: Message,
    user_query: str,
    needs_web: bool = False,
    search_query: Optional[str] = None,
    history: Optional[List[Dict[str, str]]] = None,
    status_msg: Optional[Message] = None
) -> str:
    """
    Осуществляет плавный потоковый вывод ответа ассистента в Telegram в реальном времени.
    - Обновляет сообщение каждые 0.35-0.5 секунды с эффектом живого набора текста (курсор ▌).
    - При быстром получении ответа обеспечивает визуальную плавность появления.
    - Редактирует сообщение НА МЕСТЕ без лишних удалений и мигания в красивый, валидный Telegram HTML.
    - Возвращает полный итоговый текст ответа для сохранения в историю диалога.
    """
    if status_msg is None:
        wait_text = (
            f"{E_SEARCH} <i>Ищу актуальную информацию в интернете...</i>"
            if needs_web
            else f"{E_THINK} <i>Думаю над ответом...</i>"
        )
        status_msg = await message.answer(wait_text)

    full_text = ""
    last_edit_time = 0.0
    last_edited_len = 0
    edit_count = 0
    last_preview = ""

    async for delta in stream_query_answer(
        user_query=user_query,
        needs_web=needs_web,
        search_query=search_query,
        history=history
    ):
        full_text += delta
        now = time.monotonic()
        # Редактируем статус не чаще раза в 0.4с и только при заметном приросте текста,
        # иначе Telegram начинает возвращать RetryAfter и сообщение мигает.
        min_interval = 0.4
        min_chars = 40 if last_edited_len == 0 else 60

        if (now - last_edit_time >= min_interval) and (len(full_text) - last_edited_len >= min_chars):
            preview = clean_for_preview(full_text)
            if preview and preview != last_preview:
                try:
                    await status_msg.edit_text((preview + " ▌")[:4000], parse_mode=None)
                    last_edit_time = now
                    last_edited_len = len(full_text)
                    last_preview = preview
                    edit_count += 1
                except TelegramBadRequest:
                    # текст не изменился или слишком часто — просто пропускаем кадр
                    last_edit_time = now
                except Exception as exc:  # noqa: BLE001
                    logger.debug("Пропускаем промежуточный кадр: %s", exc)
                    last_edit_time = now

    # Резерв, если ничего не вернулось
    if not full_text.strip():
        full_text = await answer_query(
            user_query=user_query,
            needs_web=needs_web,
            search_query=search_query,
            history=history
        )

    await send_rich_response(
        bot=message.bot,
        chat_id=message.chat.id,
        raw_markdown=full_text,
        status_msg=status_msg
    )

    return full_text
