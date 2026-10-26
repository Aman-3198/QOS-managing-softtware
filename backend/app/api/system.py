"""System info endpoint. Read-only; uses stdlib + a single nmcli call (cached)."""
from __future__ import annotations

import os
import platform
import subprocess
from functools import lru_cache

from fastapi import APIRouter

from ..core.constants import EXEC_PATHS
from ..schemas import SystemInfo

router = APIRouter(prefix="/system", tags=["system"])


def _read_os_release() -> dict[str, str]:
    info: dict[str, str] = {}
    try:
        with open("/etc/os-release", encoding="utf-8") as f:
            for line in f:
                if "=" in line:
                    k, v = line.strip().split("=", 1)
                    info[k] = v.strip('"')
    except OSError:
        pass
    return info


def _cpu_info() -> tuple[str | None, int | None]:
    model = None
    count = None
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as f:
            n = 0
            for line in f:
                if line.startswith("model name"):
                    if model is None:
                        model = line.split(":", 1)[1].strip()
                    n += 1
        count = n or None
    except OSError:
        pass
    return model, count


def _mem_total_mb() -> int | None:
    try:
        with open("/proc/meminfo", encoding="utf-8") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    kb = int(line.split()[1])
                    return kb // 1024
    except (OSError, ValueError, IndexError):
        pass
    return None


def _nmcli_version() -> str | None:
    nmcli = EXEC_PATHS["nmcli"]
    if not os.path.exists(nmcli):
        return None
    try:
        out = subprocess.run(
            [nmcli, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        for line in (out.stdout or "").splitlines():
            if "version" in line.lower():
                return line.strip()
        return (out.stdout or "").strip().splitlines()[0] if out.stdout else None
    except (subprocess.SubprocessError, OSError):
        return None


@lru_cache(maxsize=1)
def _gather() -> SystemInfo:
    model, count = _cpu_info()
    osr = _read_os_release()
    return SystemInfo(
        hostname=platform.node() or None,
        os=osr.get("PRETTY_NAME") or osr.get("NAME"),
        os_codename=osr.get("VERSION_CODENAME"),
        kernel=platform.release() or None,
        arch=platform.machine() or None,
        cpu_model=model,
        cpu_count=count,
        mem_total_mb=_mem_total_mb(),
        nm_version=_nmcli_version(),
        python_version=platform.python_version(),
    )


@router.get("/info", response_model=SystemInfo)
def system_info() -> SystemInfo:
    return _gather()
