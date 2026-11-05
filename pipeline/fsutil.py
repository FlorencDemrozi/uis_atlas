"""Safe file writes and reads shared by all pipeline stages.

A stage can be killed at any moment (run_weekly.py's time limit, a reboot, OneDrive
locking a file). Writing to a temporary file and renaming it means a reader only ever
sees the old file or the complete new one, never a truncated one. JSONL files are
appended to, so the reader skips a half-written last line instead of failing forever.
"""
import json
import os
import time
from collections.abc import Iterable, Iterator
from pathlib import Path


def _replace(tmp: Path, path: Path, attempts: int = 5) -> None:
    """os.replace, retried briefly: on Windows a sync client or virus scanner can hold
    the target open for a moment."""
    for i in range(attempts):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if i == attempts - 1:
                raise
            time.sleep(0.5 * (i + 1))


def write_text(path: Path, text: str) -> None:
    """Write text atomically (temporary file in the same folder, then rename)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    _replace(tmp, path)


def write_json(path: Path, obj, *, indent: int | None = None, ensure_ascii: bool = False) -> None:
    """json.dumps(obj) written atomically."""
    write_text(path, json.dumps(obj, ensure_ascii=ensure_ascii, indent=indent))


def write_bytes(path: Path, data: bytes) -> None:
    """Write bytes atomically."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    _replace(tmp, path)


def write_jsonl(path: Path, records: Iterable) -> None:
    """Write a whole JSONL file atomically."""
    write_text(path, "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records))


def append_jsonl(path: Path, records: Iterable) -> None:
    """Append records to a JSONL file. If an earlier run was killed mid-line, start on a
    new line so the broken fragment stays on its own (read_jsonl skips it)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    needs_newline = False
    if path.exists() and path.stat().st_size:
        with path.open("rb") as f:
            f.seek(-1, os.SEEK_END)
            needs_newline = f.read(1) != b"\n"
    with path.open("a", encoding="utf-8", newline="\n") as f:
        if needs_newline:
            f.write("\n")
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
        f.flush()


def read_jsonl(path: Path) -> Iterator:
    """Records of a JSONL file; lines that are not valid JSON (a write cut off by a
    kill) are skipped with a warning instead of stopping every later run."""
    bad = 0
    with Path(path).open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                bad += 1
    if bad:
        print(f"Warning: skipped {bad} broken line(s) in {Path(path).name} (an interrupted write).")
