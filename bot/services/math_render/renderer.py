import os
import sys
import json
import base64
import hashlib
import asyncio
import logging
from dataclasses import dataclass
from typing import Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "cache" / "math_images"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

SCRIPT_PATH = Path(__file__).resolve().parent / "render_script.js"

# In-memory LRU-like cache: hash -> (png_bytes, width, height)
_MEMORY_CACHE = {}
_MAX_MEMORY_CACHE = 500


@dataclass
class RenderedFormula:
    latex: str
    image_path: str
    png_bytes: bytes
    width: int
    height: int

    @property
    def is_extreme_aspect_ratio(self) -> bool:
        """Returns True if aspect ratio is too extreme (e.g. > 4.5:1), suggesting sendDocument."""
        if self.height <= 0 or self.width <= 0:
            return False
        ratio = max(self.width / self.height, self.height / self.width)
        return ratio > 4.5


class MathRenderer:
    """
    Manages asynchronous rendering of LaTeX formulas to PNG using Node.js + MathJax + resvg.
    Includes 2-level caching (RAM + disk), subprocess pooling/daemon, and timeouts.
    """
    def __init__(self):
        self._daemon_process: Optional[asyncio.subprocess.Process] = None
        self._lock = asyncio.Lock()
        self._req_counter = 0

    async def close(self):
        """Gracefully closes the daemon process if running."""
        async with self._lock:
            if self._daemon_process:
                try:
                    if self._daemon_process.stdin and not self._daemon_process.stdin.is_closing():
                        self._daemon_process.stdin.close()
                    self._daemon_process.terminate()
                except Exception:
                    pass
                self._daemon_process = None

    def _sync_cleanup(self):
        if self._daemon_process:
            try:
                self._daemon_process.kill()
            except (Exception, OSError):
                pass
            self._daemon_process = None

    def _is_daemon_alive(self) -> bool:
        if not self._daemon_process or self._daemon_process.returncode is not None:
            return False
        if self._daemon_process.stdin is None or self._daemon_process.stdin.is_closing():
            return False
        try:
            current_loop = asyncio.get_running_loop()
            if getattr(self._daemon_process, '_loop', None) != current_loop:
                return False
        except Exception:
            return False
        return True

    async def _ensure_daemon(self) -> asyncio.subprocess.Process:
        if self._is_daemon_alive():
            return self._daemon_process

        if self._daemon_process:
            try:
                self._daemon_process.kill()
            except Exception:
                pass
            self._daemon_process = None

        try:
            self._daemon_process = await asyncio.create_subprocess_exec(
                "node",
                str(SCRIPT_PATH),
                "--daemon",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL
            )
            logger.info("MathRenderer Node.js daemon started successfully")
            return self._daemon_process
        except Exception as e:
            logger.warning(f"Failed to start MathRenderer Node daemon: {e}")
            self._daemon_process = None
            raise

    def _get_hash(self, latex: str) -> str:
        cleaned = latex.strip()
        return hashlib.sha256(cleaned.encode("utf-8")).hexdigest()

    async def render(self, latex: str, timeout: float = 5.0) -> RenderedFormula:
        """
        Renders a LaTeX formula to PNG.
        Returns RenderedFormula on success or raises Exception on failure/timeout.
        """
        cleaned_latex = latex.strip()
        if not cleaned_latex:
            raise ValueError("LaTeX string is empty")

        formula_hash = self._get_hash(cleaned_latex)
        out_file = CACHE_DIR / f"{formula_hash}.png"

        # 1. Check memory cache
        if formula_hash in _MEMORY_CACHE:
            png_bytes, width, height = _MEMORY_CACHE[formula_hash]
            return RenderedFormula(
                latex=cleaned_latex,
                image_path=str(out_file),
                png_bytes=png_bytes,
                width=width,
                height=height
            )

        # 2. Check disk cache
        if out_file.exists():
            try:
                png_bytes = out_file.read_bytes()
                # Basic PNG dimension reader without heavy imports
                width, height = self._read_png_dimensions(png_bytes)
                _MEMORY_CACHE[formula_hash] = (png_bytes, width, height)
                return RenderedFormula(
                    latex=cleaned_latex,
                    image_path=str(out_file),
                    png_bytes=png_bytes,
                    width=width,
                    height=height
                )
            except Exception as e:
                logger.warning(f"Error reading cached formula {out_file}: {e}")

        # 3. Render via daemon or CLI fallback
        try:
            rendered = await asyncio.wait_for(
                self._render_with_daemon(cleaned_latex, str(out_file)),
                timeout=timeout
            )
        except Exception as daemon_err:
            logger.debug(f"Daemon render failed ({daemon_err}), trying CLI fallback...")
            rendered = await asyncio.wait_for(
                self._render_with_cli(cleaned_latex, str(out_file)),
                timeout=timeout
            )

        # Save to memory cache
        if len(_MEMORY_CACHE) >= _MAX_MEMORY_CACHE:
            # Evict oldest
            first_key = next(iter(_MEMORY_CACHE))
            del _MEMORY_CACHE[first_key]
        _MEMORY_CACHE[formula_hash] = (rendered.png_bytes, rendered.width, rendered.height)

        return rendered

    async def _render_with_daemon(self, latex: str, out_path: str) -> RenderedFormula:
        async with self._lock:
            proc = await self._ensure_daemon()
            self._req_counter += 1
            req_id = self._req_counter
            req_obj = {
                "id": req_id,
                "latex": latex,
                "outPath": out_path
            }

            try:
                req_line = json.dumps(req_obj) + "\n"
                proc.stdin.write(req_line.encode("utf-8"))
                await proc.stdin.drain()

                res_line = await proc.stdout.readline()
                if not res_line:
                    self._daemon_process = None
                    raise RuntimeError("Math renderer daemon closed stdout unexpectedly")

                res = json.loads(res_line.decode("utf-8").strip())
                if not res.get("success"):
                    raise ValueError(res.get("error", "Unknown render error"))
            except Exception as e:
                # If communication failed, ensure daemon reference is cleared
                if not isinstance(e, ValueError):
                    self._daemon_process = None
                raise

            png_bytes = Path(out_path).read_bytes()
            return RenderedFormula(
                latex=latex,
                image_path=out_path,
                png_bytes=png_bytes,
                width=res.get("width", 600),
                height=res.get("height", 200)
            )

    async def _render_with_cli(self, latex: str, out_path: str) -> RenderedFormula:
        b64_latex = base64.b64encode(latex.encode("utf-8")).decode("ascii")
        proc = await asyncio.create_subprocess_exec(
            "node",
            str(SCRIPT_PATH),
            "--base64",
            b64_latex,
            out_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            err_msg = stderr.decode("utf-8").strip() or stdout.decode("utf-8").strip()
            try:
                err_json = json.loads(err_msg)
                err_text = err_json.get("error", err_msg)
            except Exception:
                err_text = err_msg
            raise ValueError(f"LaTeX rendering failed: {err_text}")

        res = json.loads(stdout.decode("utf-8").strip())
        png_bytes = Path(out_path).read_bytes()
        return RenderedFormula(
            latex=latex,
            image_path=out_path,
            png_bytes=png_bytes,
            width=res.get("width", 600),
            height=res.get("height", 200)
        )

    def _read_png_dimensions(self, png_bytes: bytes) -> Tuple[int, int]:
        """Extract width and height from PNG IHDR chunk without PIL dependency."""
        if len(png_bytes) >= 24 and png_bytes[:8] == b'\x89PNG\r\n\x1a\n':
            width = int.from_bytes(png_bytes[16:20], byteorder='big')
            height = int.from_bytes(png_bytes[20:24], byteorder='big')
            return width, height
        return 600, 200


_renderer_instance = MathRenderer()
import atexit
atexit.register(_renderer_instance._sync_cleanup)


async def render_latex_to_png(latex: str, timeout: float = 5.0) -> RenderedFormula:
    """Global convenience helper to render LaTeX formula to PNG."""
    return await _renderer_instance.render(latex, timeout=timeout)
