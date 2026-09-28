import unittest
import asyncio
from pathlib import Path
from bot.services.math_render.renderer import render_latex_to_png, MathRenderer


class TestMathRender(unittest.IsolatedAsyncioTestCase):

    async def test_render_valid_formula(self):
        """Проверка успешного рендера формулы в PNG."""
        latex = r"\int_{-\infty}^{+\infty} e^{-x^2} dx = \sqrt{\pi}"
        result = await render_latex_to_png(latex)
        self.assertIsNotNone(result)
        self.assertTrue(result.png_bytes.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertGreater(result.width, 100)
        self.assertGreater(result.height, 50)
        self.assertTrue(Path(result.image_path).exists())

    async def test_render_caching(self):
        """Повторный запрос той же формулы должен браться из кэша."""
        latex = r"\sum_{k=1}^n k = \frac{n(n+1)}{2}"
        res1 = await render_latex_to_png(latex)
        res2 = await render_latex_to_png(latex)
        self.assertEqual(res1.image_path, res2.image_path)
        self.assertEqual(res1.png_bytes, res2.png_bytes)
        self.assertEqual(res1.width, res2.width)

    async def test_invalid_latex_raises(self):
        """Невалидный LaTeX должен выбрасывать ошибку, позволяя сработать фолбэку."""
        broken_latex = r"\frac{incomplete"
        with self.assertRaises(Exception):
            await render_latex_to_png(broken_latex)


if __name__ == "__main__":
    unittest.main()
