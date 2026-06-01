import sys
import time

import httpx

from larvis.config import settings
from larvis.server import main


def _check_vault() -> None:
    from pathlib import Path
    vault = Path(settings.vault_path)
    if not vault.exists():
        print(f"ERROR: Vault path not found: {vault}", flush=True)
        sys.exit(1)


def _wait_for_ollama() -> None:
    print("Waiting for Ollama...", flush=True)
    for i in range(5):
        try:
            r = httpx.get(f"{settings.ollama_host}/api/tags", timeout=5)
            if r.status_code == 200:
                print("Ollama ready.", flush=True)
                return
        except Exception:
            pass
        if i < 4:
            print(f"  retry {i + 1}/5...", flush=True)
            time.sleep(3)
    print("ERROR: Ollama not ready after 5 retries.", flush=True)
    sys.exit(1)


if __name__ == "__main__":
    _check_vault()
    _wait_for_ollama()
    main()
