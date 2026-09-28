import unittest
from bot.services.rich_message.converter import markdown_to_rich_html, is_likely_math


class TestRichConverter(unittest.TestCase):

    def test_consecutive_block_formulas(self):
        """Несколько $$...$$ подряд без текста или с переносами строк."""
        text = (
            "$$\\int_0^1 x^2 dx = \\frac{1}{3}$$\n\n"
            "$$\\sum_{n=1}^\\infty \\frac{1}{n^2} = \\frac{\\pi^2}{6}$$"
        )
        html = markdown_to_rich_html(text)
        self.assertIn("<tg-math-block>\\int_0^1 x^2 dx = \\frac{1}{3}</tg-math-block>", html)
        self.assertIn("<tg-math-block>\\sum_{n=1}^\\infty \\frac{1}{n^2} = \\frac{\\pi^2}{6}</tg-math-block>", html)
        # Проверяем, что оба блока присутствуют в правильном порядке
        pos1 = html.find("\\int_0^1")
        pos2 = html.find("\\sum_{n=1}")
        self.assertLess(pos1, pos2)

    def test_dollars_in_code_blocks_and_inline_code(self):
        """$ внутри блоков кода и inline-кода не должны превращаться в формулы."""
        text = (
            "Команда в терминале:\n"
            "`export PATH=$PATH:/usr/local/bin`\n\n"
            "Скрипт:\n"
            "```bash\n"
            "echo $USER\n"
            "VAR=$((VAR + 1))\n"
            "```"
        )
        html = markdown_to_rich_html(text)
        self.assertIn("<code>export PATH=$PATH:/usr/local/bin</code>", html)
        self.assertIn('<pre><code class="language-bash">echo $USER\nVAR=$((VAR + 1))</code></pre>', html)
        self.assertNotIn("<tg-math>", html)
        self.assertNotIn("<tg-math-block>", html)

    def test_dollars_in_prices(self):
        """Цены вида $5, $10.99, $100 не должны превращаться в формулы."""
        text = "Билет стоит $5, обед $10.99, а аренда от $50 до $100."
        html = markdown_to_rich_html(text)
        self.assertIn("$5", html)
        self.assertIn("$10.99", html)
        self.assertIn("$50", html)
        self.assertIn("$100", html)
        self.assertNotIn("<tg-math>", html)

    def test_formulas_at_start_and_end_of_text(self):
        """Формулы в самом начале и в самом конце сообщения."""
        text = (
            "$$\\int e^x dx = e^x + C$$\n"
            "Пояснение в середине.\n"
            "$$\\int \\frac{1}{x} dx = \\ln|x| + C$$"
        )
        html = markdown_to_rich_html(text)
        self.assertTrue(html.startswith("<tg-math-block>\\int e^x dx = e^x + C</tg-math-block>"))
        self.assertTrue(html.endswith("<tg-math-block>\\int \\frac{1}{x} dx = \\ln|x| + C</tg-math-block>"))
        self.assertIn("Пояснение в середине.", html)

    def test_nested_curly_braces(self):
        """Формулы с глубокой вложенностью фигурных скобок."""
        text = "$$\\frac{\\sqrt{x^2 + \\frac{1}{x^2}}}{e^{\\sin(x^2)}} = 1$$"
        html = markdown_to_rich_html(text)
        self.assertIn(
            "<tg-math-block>\\frac{\\sqrt{x^2 + \\frac{1}{x^2}}}{e^{\\sin(x^2)}} = 1</tg-math-block>",
            html
        )

    def test_symbols_less_and_ampersand_inside_formula(self):
        """Символы <, > и & внутри формул должны экранироваться (&lt;, &gt;, &amp;)."""
        text = "$$x < 5 \\quad \\& \\quad y > 2$$\nИнлайн: $a < b \\& c > d$."
        html = markdown_to_rich_html(text)
        # Внутри блочной формулы
        self.assertIn("<tg-math-block>x &lt; 5 \\quad \\&amp; \\quad y &gt; 2</tg-math-block>", html)
        # Внутри строчной формулы
        self.assertIn("<tg-math>a &lt; b \\&amp; c &gt; d</tg-math>", html)

    def test_numbered_headings(self):
        """Нумерованные заголовки вроде «1. **Ряд Софуса**» должны оставаться жирными заголовками."""
        text = (
            "# Главный заголовок\n\n"
            "1. **Интеграл Пуассона (Гаусса)**\n"
            "Вычисляется через полярные координаты.\n\n"
            "2. **Интеграл Дирихле**\n"
            "Условно сходящийся интеграл."
        )
        html = markdown_to_rich_html(text)
        self.assertIn("<h1>Главный заголовок</h1>", html)
        self.assertIn("<b>1. Интеграл Пуассона (Гаусса)</b>", html)
        self.assertIn("<b>2. Интеграл Дирихле</b>", html)

    def test_inline_formula(self):
        """Строчные формулы $...$ и \\(...\\) корректно преобразуются в <tg-math>."""
        text = "Пусть $x^2 + y^2 = 1$ и \\(\\alpha = \\pi/4\\)."
        html = markdown_to_rich_html(text)
        self.assertIn("<tg-math>x^2 + y^2 = 1</tg-math>", html)
        self.assertIn("<tg-math>\\alpha = \\pi/4</tg-math>", html)


if __name__ == "__main__":
    unittest.main()
