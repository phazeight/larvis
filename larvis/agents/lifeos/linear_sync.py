import re
import subprocess
from pathlib import Path

from larvis.agents.lifeos.memory import is_task_synced, mark_task_synced
from larvis.config import settings

_TASK_PATTERN = re.compile(r"^- \[ \] (.+)$", re.MULTILINE)
_TAG = "#to-linear"


def scan_vault_for_tagged_tasks(vault_path: Path) -> list[dict]:
    tasks = []
    for md_file in vault_path.rglob("*.md"):
        try:
            content = md_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for match in _TASK_PATTERN.finditer(content):
            line = match.group(1)
            if _TAG not in line:
                continue
            task_text = line.replace(_TAG, "").strip()
            tasks.append({
                "vault_file": str(md_file.relative_to(vault_path)),
                "task_text": task_text,
            })
    return tasks


def sync_tasks() -> int:
    vault = Path(settings.vault_path)
    tasks = scan_vault_for_tagged_tasks(vault)
    synced = 0
    for task in tasks:
        if is_task_synced(task["vault_file"], task["task_text"]):
            continue
        try:
            result = subprocess.run(
                ["lb", "create", task["task_text"]],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                continue
            parts = result.stdout.strip().split()
            linear_id = parts[-1] if parts else "unknown"
            mark_task_synced(task["vault_file"], task["task_text"], linear_id)
            synced += 1
        except FileNotFoundError:
            raise RuntimeError(
                "lb not found — install with:\n"
                "  bun install -g github:nikvdp/linear-beads\n"
                "then run: lb onboard"
            )
        except subprocess.TimeoutExpired:
            continue
    if synced > 0:
        subprocess.run(["lb", "sync"], capture_output=True, text=True, timeout=30)
    return synced
