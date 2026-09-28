import unittest
from bot.services.message_splitter import parse_response_segments, is_complex_formula, Segment


class TestMessageSplitter(unittest.TestCase):

    def test_consecutive_block_formulas(self):
        """Несколько $$...$$ подряд без текста или только с пробелами/переносами."""
        text = "$$\\int_0^1 x^2 dx = \\frac{1}{3}$$\n\n$$\\sum_{n=1}^\\infty \\frac{1}{n^2} = \\frac{\\pi^2}{6}$$"
        segments = parse_response_segments(text)
        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0].type, "formula")
        self.assertIn(r"\int_0^1", segments[0].content)
        self.assertEqual(segments[1].type, "formula")
        self.assertIn(r"\sum_{n=1}", segments[1].content)

    def test_dollars_in_code_blocks_and_inline_code(self):
        """$ внутри блоков кода и inline-кода не должны ломать парсер."""
        text = (
            "Команда для проверки переменной:\n"
            "`export PATH=$PATH:/usr/local/bin`\n\n"
            "А вот скрипт:\n"
            "```bash\n"
            "echo $USER\n"
            "COUNT=$((COUNT + 1))\n"
            "```\n"
            "Конец блока."
        )
        segments = parse_response_segments(text)
        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0].type, "text")
        self.assertIn("<code>export PATH=$PATH:/usr/local/bin</code>", segments[0].content)
        self.assertIn("<pre><code class=\"language-bash\">echo $USER\nCOUNT=$((COUNT + 1))</code></pre>", segments[0].content)

    def test_dollars_in_prices(self):
        """Цены вида $5, $10.99, $100 не должны превращаться в формулы."""
        text = "Билет стоит $5, а премиум — $10.99. Итого $15.99."
        segments = parse_response_segments(text)
        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0].type, "text")
        self.assertIn("$5", segments[0].content)
        self.assertIn("$10.99", segments[0].content)
        self.assertIn("$15.99", segments[0].content)

    def test_formulas_at_start_and_end_of_text(self):
        """Формулы в самом начале и в самом конце сообщения."""
        text = (
            "$$\\int e^x dx = e^x + C$$\n"
            "Пояснение между формулами.\n"
            "$$\\int \\frac{1}{x} dx = \\ln|x| + C$$"
        )
        segments = parse_response_segments(text)
        self.assertEqual(len(segments), 3)
        self.assertEqual(segments[0].type, "formula")
        self.assertIn(r"\int e^x", segments[0].content)
        self.assertEqual(segments[1].type, "text")
        self.assertIn("Пояснение между формулами.", segments[1].content)
        self.assertEqual(segments[2].type, "formula")
        self.assertIn(r"\int \frac{1}{x}", segments[2].content)

    def test_empty_text_between_formulas(self):
        """Пустой текст или только пробелы/табы между формулами не должны создавать пустых сегментов."""
        text = "$$A = B$$     \t\n   \n   \t  $$C = D$$"
        segments = parse_response_segments(text)
        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0].type, "formula")
        self.assertEqual(segments[0].content, "A = B")
        self.assertEqual(segments[1].type, "formula")
        self.assertEqual(segments[1].content, "C = D")

    def test_nested_curly_braces(self):
        """Формула с глубокой вложенностью фигурных скобок."""
        text = "$$\\frac{\\sqrt{x^2 + \\frac{1}{x^2}}}{e^{\\sin(x^2)}} = 1$$"
        segments = parse_response_segments(text)
        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0].type, "formula")
        self.assertEqual(segments[0].content, r"\frac{\sqrt{x^2 + \frac{1}{x^2}}}{e^{\sin(x^2)}} = 1")

    def test_simple_inline_to_unicode(self):
        """Простые формулы вроде $x^2$, $\\alpha$, $a \\approx b$ остаются внутри текста в виде Unicode."""
        text = "Пусть дана переменная $x^2$ и угол $\\alpha \\approx \\pi/4$."
        segments = parse_response_segments(text)
        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0].type, "text")
        # x^2 -> x², \alpha -> α
        self.assertIn("x²", segments[0].content)
        self.assertIn("α", segments[0].content)

    def test_complex_inline_extracted_to_formula(self):
        """Сложные формулы внутри строки (интеграл, дробь, сумма, корень) выносятся в formula."""
        text = "Рассмотрим интеграл $\\int_0^1 x^2 dx$ и затем дробь $\\frac{a+b}{c}$."
        segments = parse_response_segments(text)
        self.assertEqual(len(segments), 4)
        self.assertEqual(segments[0].type, "text")
        self.assertIn("Рассмотрим интеграл", segments[0].content)
        self.assertEqual(segments[1].type, "formula")
        self.assertIn(r"\int_0^1", segments[1].content)
        self.assertEqual(segments[2].type, "text")
        self.assertIn("и затем дробь", segments[2].content)
        self.assertEqual(segments[3].type, "formula")
        self.assertIn(r"\frac{a+b}{c}", segments[3].content)

    def test_strict_order_preservation(self):
        """Порядок сегментов сохраняется строго."""
        text = (
            "# Заголовок\n\n"
            "Вводный текст.\n"
            "$$\\int f(x) dx$$\n"
            "Промежуточный текст с $y^3$.\n"
            "$$\\sum_{k=1}^n k$$\n"
            "Итоговый вывод."
        )
        segments = parse_response_segments(text)
        self.assertEqual(len(segments), 5)
        self.assertEqual(segments[0].type, "text")
        self.assertIn("<b>Заголовок</b>", segments[0].content)
        self.assertEqual(segments[1].type, "formula")
        self.assertEqual(segments[2].type, "text")
        self.assertIn("y³", segments[2].content)
        self.assertEqual(segments[3].type, "formula")
        self.assertEqual(segments[4].type, "text")
        self.assertIn("Итоговый вывод.", segments[4].content)


if __name__ == "__main__":
    unittest.main()
