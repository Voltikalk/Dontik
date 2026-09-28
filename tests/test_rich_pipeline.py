import unittest
from unittest.mock import AsyncMock, MagicMock
from aiogram import Bot
from aiogram.types import Message, InputRichMessage
from aiogram.exceptions import TelegramBadRequest

from bot.services.rich_message.converter import markdown_to_rich_html
from bot.services.rich_message.sender import send_rich_response, replace_math_tags_with_unicode


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


class TestRichPipeline(unittest.IsolatedAsyncioTestCase):

    def test_integrals_conversion_to_rich_html(self):
        """Проверка конвертации ответа с 5 интегралами в нативный Rich HTML."""
        rich_html = markdown_to_rich_html(SAMPLE_INTEGRALS_RESPONSE)

        # 1. Заголовки и нумерованные пункты
        self.assertIn("<h1>Топ-5 красивых и важных интегралов</h1>", rich_html)
        self.assertIn("<b>1. Интеграл Пуассона (Гаусса)</b>", rich_html)
        self.assertIn("<b>2. Интеграл Дирихле</b>", rich_html)
        self.assertIn("<b>5. Гамма-функция Эйлера</b>", rich_html)

        # 2. Ровно 5 блочных формул <tg-math-block>
        math_blocks = rich_html.count("<tg-math-block>")
        self.assertEqual(math_blocks, 5)

        # 3. Инлайн формулы <tg-math>
        self.assertIn("<tg-math>x^2</tg-math>", rich_html)
        self.assertIn("<tg-math>\\zeta(2)</tg-math>", rich_html)

        # 4. Общая длина не превышает лимит Rich Message (32768)
        self.assertLess(len(rich_html), 32000)

    async def test_send_rich_response_single_message_success(self):
        """Проверка отправки строго одним вызовом send_rich_message без reply."""
        bot = MagicMock(spec=Bot)
        bot.send_rich_message = AsyncMock(return_value=MagicMock(spec=Message))
        bot.send_message = AsyncMock()
        bot.send_photo = AsyncMock()

        status_msg = MagicMock(spec=Message)
        status_msg.delete = AsyncMock()

        chat_id = 987654321

        sent = await send_rich_response(
            bot=bot,
            chat_id=chat_id,
            raw_markdown=SAMPLE_INTEGRALS_RESPONSE,
            status_msg=status_msg
        )

        # Статусное сообщение удалено
        status_msg.delete.assert_called_once()

        # Ровно один вызов send_rich_message
        self.assertEqual(bot.send_rich_message.call_count, 1)

        # Никаких картинок и sendMessage
        bot.send_photo.assert_not_called()
        bot.send_message.assert_not_called()

        call_args = bot.send_rich_message.call_args
        self.assertEqual(call_args.kwargs["chat_id"], chat_id)
        rich_obj = call_args.kwargs["rich_message"]
        self.assertIsInstance(rich_obj, InputRichMessage)
        self.assertIn("<tg-math-block>", rich_obj.html)

    async def test_send_rich_fallback_on_invalid_latex(self):
        """Если send_rich_message упал, срабатывает фолбэк на Unicode формулы."""
        bot = MagicMock(spec=Bot)

        # Первый вызов падает (симуляция ошибки невалидного LaTeX в Telegram)
        bot.send_rich_message = AsyncMock(side_effect=[
            TelegramBadRequest(method=MagicMock(), message="Bad Request: invalid LaTeX syntax"),
            MagicMock(spec=Message)  # Второй вызов (фолбэк с Unicode) успешен
        ])
        bot.send_message = AsyncMock()

        broken_markdown = "Формула: $$\\broken{latex$$"
        sent = await send_rich_response(
            bot=bot,
            chat_id=123,
            raw_markdown=broken_markdown
        )

        # Должно быть 2 вызова send_rich_message (первый сбой, второй успешен с фолбэком)
        self.assertEqual(bot.send_rich_message.call_count, 2)
        second_call = bot.send_rich_message.call_args_list[1]
        html_payload = second_call.kwargs["rich_message"].html
        # В фолбэке теги <tg-math-block> должны быть заменены на <blockquote><b>
        self.assertNotIn("<tg-math-block>", html_payload)
        self.assertIn("<blockquote><b>", html_payload)


if __name__ == "__main__":
    unittest.main()
