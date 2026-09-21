import asyncio
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


def _sync_ddg_search(query: str, max_results: int = 4) -> List[Dict[str, str]]:
    """Синхронный вызов DDGS для поиска в отдельном потоке с таймаутом."""
    try:
        from ddgs import DDGS
        with DDGS(timeout=4) as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
            clean_results = []
            for r in results:
                title = r.get("title", "").strip()
                body = r.get("body", "").strip()
                href = r.get("href", "").strip()
                if title or body:
                    clean_results.append({
                        "title": title,
                        "body": body,
                        "href": href
                    })
            return clean_results
    except Exception as e:
        logger.warning(f"Ошибка при выполнении веб-поиска DuckDuckGo для запроса «{query}»: {e}")
        return []


async def search_web(query: str, max_results: int = 4) -> List[Dict[str, str]]:
    """
    Асинхронная обертка для поиска в интернете через DuckDuckGo (ddgs).
    Выполняется в фоновом пуле потоков с жестким таймаутом 4.5 секунды, не блокируя event loop бота.
    """
    clean_query = query.strip()
    if not clean_query:
        return []

    try:
        results = await asyncio.wait_for(
            asyncio.to_thread(_sync_ddg_search, clean_query, max_results),
            timeout=4.5
        )
        logger.info(f"Веб-поиск по запросу «{clean_query}» вернул {len(results)} результатов")
        return results
    except asyncio.TimeoutError:
        logger.warning(f"Таймаут веб-поиска для запроса «{clean_query}» (>4.5с), продолжаем без интернета")
        return []
    except Exception as e:
        logger.error(f"Непредвиденная ошибка в search_web: {e}", exc_info=True)
        return []
