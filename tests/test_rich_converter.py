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

    def test_markdown_lists(self):
        """Маркированные списки превращаются в <ul><li>...</li></ul>."""
        text = "- Пункт 1\n- Пункт 2\n- Пункт 3"
        html = markdown_to_rich_html(text)
        self.assertIn("<ul>", html)
        self.assertIn("<li>Пункт 1", html)
        self.assertIn("<li>Пункт 2", html)
        self.assertIn("<li>Пункт 3", html)
        self.assertIn("</ul>", html)

    def test_nested_lists(self):
        """Вложенные списки с отступами корректно иерархически оборачиваются."""
        text = (
            "- Кинематика\n"
            "  - Равномерное движение\n"
            "  - Равноускоренное движение\n"
            "- Динамика\n"
            "  - Законы Ньютона"
        )
        html = markdown_to_rich_html(text)
        self.assertIn("<ul>", html)
        self.assertIn("<li>Кинематика", html)
        self.assertIn("<li>Равномерное движение", html)
        self.assertIn("<li>Равноускоренное движение", html)
        self.assertIn("<li>Динамика", html)
        self.assertIn("<li>Законы Ньютона", html)

    def test_headings(self):
        """Заголовки #, ##, ### преобразуются в h1, h2, h3."""
        text = "# Заголовок 1\n\n## Заголовок 2\n\n### Заголовок 3"
        html = markdown_to_rich_html(text)
        self.assertIn("<h1>Заголовок 1</h1>", html)
        self.assertIn("<h2>Заголовок 2</h2>", html)
        self.assertIn("<h3>Заголовок 3</h3>", html)

    def test_single_and_double_newlines(self):
        """Двойной перенос создает отдельные <p>, одиночный создает <br> внутри <p>."""
        text = (
            "Первый абзац, первая строка.\n"
            "Первый абзац, вторая строка.\n\n"
            "Второй абзац."
        )
        html = markdown_to_rich_html(text)
        self.assertIn("<p>Первый абзац, первая строка.<br>Первый абзац, вторая строка.</p>", html)
        self.assertIn("<p>Второй абзац.</p>", html)

    def test_bold_inside_list_item(self):
        """Жирный шрифт выделяет только термин внутри пункта списка, не протекая дальше."""
        text = (
            "- **Закон Ома** — сила тока пропорциональна напряжению.\n"
            "- **Закон Джоуля-Ленца** — количество теплоты."
        )
        html = markdown_to_rich_html(text)
        self.assertIn("<li><b>Закон Ома</b> — сила тока пропорциональна напряжению.</li>", html)
        self.assertIn("<li><b>Закон Джоуля-Ленца</b> — количество теплоты.</li>", html)
        # Проверяем, что нет незакрытых <b>
        self.assertEqual(html.count("<b>"), html.count("</b>"))

    def test_formula_inside_list_item(self):
        """Формула внутри пункта списка корректно преобразуется в <tg-math>."""
        text = (
            "- **Второй закон Ньютона**: $F = ma$ — основное уравнение динамики.\n"
            "- **Импульс**: $p = mv$."
        )
        html = markdown_to_rich_html(text)
        self.assertIn("<b>Второй закон Ньютона</b>: <tg-math>F = ma</tg-math> — основное уравнение динамики.", html)
        self.assertIn("<b>Импульс</b>: <tg-math>p = mv</tg-math>.", html)

    def test_squished_bullets_auto_split(self):
        """Строка со слипшимися через «•» пунктами автоматически разбивается на элементы списка."""
        text = "Кинематика: • **Скорость**: $v = at$ • **Перемещение**: $s = vt$"
        html = markdown_to_rich_html(text)
        self.assertIn("<p>Кинематика:</p>", html)
        self.assertIn("<ul>", html)
        self.assertIn("<b>Скорость</b>: <tg-math>v = at</tg-math>", html)
        self.assertIn("<b>Перемещение</b>: <tg-math>s = vt</tg-math>", html)
        self.assertNotIn("•", html)


if __name__ == "__main__":
    unittest.main()
