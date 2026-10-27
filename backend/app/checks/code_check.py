"""Compile and (for runnable C++) run generated snippets.

C++: g++ -std=c++17 -Wall -Wextra -fsyntax-only, warnings count as failures.
Runnable C++: built with -fsanitize=thread and run with a timeout; any TSan report fails.
Python: py_compile plus a Python 3.10 grammar check, since the local interpreter may be newer.
"""

import ast
import asyncio
import shutil
import sys
import tempfile
from pathlib import Path

from ..config import get_settings
from ..schemas import CodeCheck

MAX_DETAIL = 3000


def gxx_path() -> str | None:
    return shutil.which("g++")


async def _run(*args: str, cwd: str, timeout: float) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        *args, cwd=cwd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return -1, f"timed out after {timeout:.0f}s"
    return proc.returncode or 0, out.decode(errors="replace")


def _trim(text: str) -> str:
    text = text.strip()
    return text if len(text) <= MAX_DETAIL else text[:MAX_DETAIL] + "\n…(truncated)"


async def check_cpp(code: str, runnable: bool) -> CodeCheck:
    gxx = gxx_path()
    if gxx is None:
        return CodeCheck(status="not_verified", tool="skipped: g++ not installed")
    settings = get_settings()
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, "snippet.cpp").write_text(code)
        rc, out = await _run(gxx, "-std=c++17", "-Wall", "-Wextra", "-fsyntax-only", "snippet.cpp",
                             cwd=tmp, timeout=60)
        if rc != 0 or "warning:" in out:
            return CodeCheck(status="not_verified", tool="g++ -std=c++17 -Wall -Wextra -fsyntax-only",
                             detail=_trim(out) or f"exit code {rc}")
        if not runnable:
            return CodeCheck(status="verified", tool="g++ -std=c++17 -Wall -Wextra -fsyntax-only")

        rc, out = await _run(gxx, "-std=c++17", "-Wall", "-Wextra", "-g", "-O1", "-fsanitize=thread",
                             "snippet.cpp", "-o", "snippet", "-pthread", cwd=tmp, timeout=120)
        if rc != 0:
            return CodeCheck(status="not_verified", tool="g++ -fsanitize=thread (build)", detail=_trim(out))
        rc, out = await _run("./snippet", cwd=tmp, timeout=settings.code_run_timeout_s)
        if rc != 0 or "ThreadSanitizer" in out:
            return CodeCheck(status="not_verified", tool="ThreadSanitizer run",
                             detail=_trim(out) or f"exit code {rc}")
        return CodeCheck(status="verified", tool="g++ -fsanitize=thread build + run")


async def check_python(code: str) -> CodeCheck:
    tool = "py_compile + Python 3.10 grammar"
    try:
        ast.parse(code, feature_version=(3, 10))
    except SyntaxError as e:
        return CodeCheck(status="not_verified", tool=tool, detail=f"Python 3.10 grammar: line {e.lineno}: {e.msg}")
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, "snippet.py").write_text(code)
        rc, out = await _run(sys.executable, "-I", "-m", "py_compile", "snippet.py", cwd=tmp, timeout=30)
    if rc != 0:
        return CodeCheck(status="not_verified", tool=tool, detail=_trim(out))
    return CodeCheck(status="verified", tool=tool)


async def check_snippet(language: str, code: str, runnable: bool) -> CodeCheck:
    if language == "cpp":
        return await check_cpp(code, runnable)
    if language == "python":
        return await check_python(code)
    return CodeCheck(status="not_verified", tool=f"no checker for {language}")
