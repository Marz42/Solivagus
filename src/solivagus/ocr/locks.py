from __future__ import annotations

import json
import os
import platform
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


class LockError(RuntimeError):
    pass


@dataclass
class LockInfo:
    path: Path
    pid: int
    hostname: str
    started_at: str
    command: str


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        # PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def acquire_lock(path: Path, *, command: str) -> LockInfo:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            old_pid = int(payload.get("pid") or 0)
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            old_pid = 0
        if old_pid and _pid_alive(old_pid):
            raise LockError(f"lock held by live pid {old_pid}: {path}")
        path.unlink(missing_ok=True)

    info = LockInfo(
        path=path,
        pid=os.getpid(),
        hostname=platform.node() or "unknown",
        started_at=_utc_now(),
        command=command,
    )
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(
            {
                "pid": info.pid,
                "hostname": info.hostname,
                "started_at": info.started_at,
                "command": info.command,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)
    return info


def release_lock(path: Path) -> None:
    try:
        if not path.exists():
            return
        payload = json.loads(path.read_text(encoding="utf-8"))
        if int(payload.get("pid") or 0) not in {0, os.getpid()}:
            return
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        pass
    path.unlink(missing_ok=True)
