import unittest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from aiogram import Bot
from aiogram.types import Message, Chat

from bot.services.message_splitter import parse_response_segments, Segment
from bot.services.math_render.renderer import render_latex_to_png
from bot.services.math_render.sender import send_rendered_segments


SAMPLE_INTEGRALS_RESPONSE = """# Топ-5 красивых и важных интегралов

Вот подборка классических интегралов из математического анализа:

1. **Интеграл Пуассона (Гаусса)**
Вычисляется через переход к полярным координатам на плоскости:
$$\\int_{-\\infty}^{+\\infty} e^{-x^2} dx = \\sqrt{\\pi}$$
Этот интеграл лежит в основе нормального распределения в теории вероятностей.

2. **Интеграл Дирихле**
Знаменитый условно сходящийся несобственный интеграл:
$$\\int_0^\\infty \\frac{\\sin x}{x} dx = \\frac{\\pi}{2}$$
Используется при исследовании рядов Фурье.

3. **Интеграл Френеля**
Возникает в волновой оптике при расчете дифракции света:
$$\\int_0^\\infty \\cos(x^2) dx = \\sqrt{\\frac{\\pi}{8}}$$
Где $x^2$ задает квадратичную фазу волны.

4. **Базельская задача через интеграл**
Связь интеграла и дзета-функции $\\zeta(2)$:
$$\\int_0^1 \\int_0^1 \\frac{dx\\,dy}{1 - xy} = \\sum_{n=1}^\\infty \\frac{1}{n^2} = \\frac{\\pi^2}{6}$$

5. **Гамма-функция Эйлера**
Обобщение факториала для вещественных и комплексных чисел при $\\text{Re}(z) > 0$:
$$\\Gamma(z) = \\int_0^\\infty t^{z-1} e^{-t} dt$$
"""


class TestPipelineIntegrals(unittest.IsolatedAsyncioTestCase):

    def test_segmentation_order(self):
        """Проверка разбиения ответа с 5 интегралами на правильные сегменты."""
        segments = parse_response_segments(SAMPLE_INTEGRALS_RESPONSE)
        formula_segs = [s for s in segments if s.type == "formula"]
        text_segs = [s for s in segments if s.type == "text"]

        # Должно быть ровно 5 формул-блоков
        self.assertEqual(len(formula_segs), 5)
        # Проверяем, что первая формула — интеграл Гаусса
        self.assertIn(r"\int_{-\infty}^{+\infty}", formula_segs[0].content)
        # Проверяем, что 5-я формула — Гамма-функция
        self.assertIn(r"\Gamma(z)", formula_segs[4].content)

        # Проверяем строгое чередование: текст -> формула -> текст -> формула ...
        self.assertEqual(segments[0].type, "text")
        self.assertIn("<b>Топ-5 красивых и важных интегралов</b>", segments[0].content)
        self.assertEqual(segments[1].type, "formula")
        self.assertEqual(segments[2].type, "text")
        self.assertEqual(segments[3].type, "formula")

    async def test_rendering_and_caching_all_5_integrals(self):
        """Проверка рендеринга всех 5 формул и повторного получения из кэша."""
        segments = parse_response_segments(SAMPLE_INTEGRALS_RESPONSE)
        formula_segs = [s for s in segments if s.type == "formula"]

        for idx, f in enumerate(formula_segs):
            res = await render_latex_to_png(f.content)
            self.assertIsNotNone(res)
            self.assertTrue(res.png_bytes.startswith(b"\x89PNG\r\n\x1a\n"))
            self.assertLessEqual(res.width, 800)
            self.assertGreater(res.height, 30)

            # Проверяем кэш
            res_cached = await render_latex_to_png(f.content)
            self.assertEqual(res.image_path, res_cached.image_path)
            self.assertEqual(res.png_bytes, res_cached.png_bytes)

    async def test_sender_mock_calls(self):
        """Проверка отправки через send_rendered_segments с Mock Bot."""
        segments = parse_response_segments(SAMPLE_INTEGRALS_RESPONSE)

        bot = MagicMock(spec=Bot)
        bot.send_message = AsyncMock(return_value=MagicMock(spec=Message))
        bot.send_photo = AsyncMock(return_value=MagicMock(spec=Message))
        bot.send_document = AsyncMock(return_value=MagicMock(spec=Message))

        status_msg = MagicMock(spec=Message)
        status_msg.edit_text = AsyncMock()
        status_msg.delete = AsyncMock()

        chat_id = 123456789

        sent = await send_rendered_segments(
            bot=bot,
            chat_id=chat_id,
            segments=segments,
            status_msg=status_msg,
            message_delay=0.01  # быстрый тест
        )

        # Первый текстовый сегмент должен отредактировать status_msg
        status_msg.edit_text.assert_called_once()

        # Формулы должны быть отправлены через send_photo или send_document
        total_photos = bot.send_photo.call_count + bot.send_document.call_count
        self.assertEqual(total_photos, 5)

        # Последующие текстовые сегменты должны быть отправлены через bot.send_message
        self.assertGreaterEqual(bot.send_message.call_count, 4)

    async def test_fallback_on_invalid_formula(self):
        """При невалидной формуле отправляется <pre> с исходником, а бот не падает."""
        broken_response = (
            "Заголовок задачи:\n"
            "$$\\invalidmacro{123$$\n"
            "Заключение после формулы."
        )
        segments = parse_response_segments(broken_response)
        self.assertEqual(len(segments), 3)
        self.assertEqual(segments[1].type, "formula")

        bot = MagicMock(spec=Bot)
        bot.send_message = AsyncMock(return_value=MagicMock(spec=Message))
        bot.send_photo = AsyncMock(return_value=MagicMock(spec=Message))

        sent = await send_rendered_segments(
            bot=bot,
            chat_id=123,
            segments=segments,
            status_msg=None,
            message_delay=0.01
        )

        # Формула упала, поэтому fallback должен вызвать bot.send_message с <pre><code>
        pre_calls = [
            call for call in bot.send_message.call_args_list
            if "<pre><code>" in call.kwargs.get("text", "")
        ]
        self.assertEqual(len(pre_calls), 1)
        self.assertIn(r"\invalidmacro{123", pre_calls[0].kwargs["text"])


if __name__ == "__main__":
    unittest.main()
