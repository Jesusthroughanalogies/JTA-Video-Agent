"""Crash-safe file storage.

Every write here survives the process being killed at any instant:
- JSON files are written to a temp file, fsynced, then atomically renamed over
  the old one. A reader sees either the old file or the new one, never half.
- Logs are append-only JSON lines, fsynced per line. A torn last line (killed
  mid-write) is skipped on read.
- EpisodeLock uses flock, which the OS releases when the process dies, even on
  kill -9, so a crash never leaves a stale lock behind.
"""
from __future__ import annotations

import fcntl
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterator


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2, sort_keys=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        _fsync_dir(path.parent)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    with open(path) as f:
        return json.load(f)


def append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, separators=(",", ":")) + "\n"
    with open(path, "a") as f:
        f.write(line)
        f.flush()
        os.fsync(f.fileno())


def read_jsonl(path: Path) -> Iterator[dict]:
    if not path.exists():
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                # Torn final line from a kill mid-append: ignore it.
                continue


def _fsync_dir(d: Path) -> None:
    try:
        fd = os.open(d, os.O_DIRECTORY)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class LockedError(RuntimeError):
    pass


class EpisodeLock:
    """One running process per episode. Released automatically if we die."""

    def __init__(self, path: Path):
        self.path = path
        self._fh = None

    def __enter__(self) -> "EpisodeLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self.path, "a+")
        try:
            fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self._fh.seek(0)
            holder = self._fh.read().strip() or "another process"
            self._fh.close()
            raise LockedError(f"episode is already running ({holder})")
        self._fh.seek(0)
        self._fh.truncate()
        self._fh.write(f"pid {os.getpid()}")
        self._fh.flush()
        return self

    def __exit__(self, *exc) -> None:
        if self._fh:
            fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
            self._fh.close()
