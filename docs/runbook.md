# Larvis Runbook — How to Know It's Working

A human-friendly guide for starting, checking, and querying Larvis.

---

## Prerequisites

Before any of this works, two things must be running:

**1. Ollama (native Mac app)**
Look for the Ollama icon in your Mac menu bar. If it's not there:
```bash
open -a Ollama
```
Verify it's up:
```bash
ollama list
```
Expected: shows `llama3.1:8b` and `nomic-embed-text` in the list.

**2. Docker containers (chromadb + larvis)**
```bash
cd ~/repos/larvis
docker compose up -d
docker compose ps
```
Expected: `larvis-chromadb-1` and `larvis-larvis-1` both show `Up`.

---

## 1. Health check — is everything connected?

```bash
uv run larvis status
```

**What healthy looks like:**
```json
{
  "ollama": true,
  "chromadb": true,
  "index_docs": 959,
  "model": "llama3.1:8b",
  "embed_model": "nomic-embed-text"
}
```

**What each field means:**
| Field | Healthy | Broken |
|-------|---------|--------|
| `ollama` | `true` | `false` — Ollama app not running |
| `chromadb` | `true` | `false` — Docker not running |
| `index_docs` | `> 0` | `0` — vault not indexed yet, run `larvis reindex` |

---

## 2. Index your vault — first time and after vault changes

```bash
uv run larvis reindex
```

Expected output:
```
Indexing vault...
Done — 959 chunks indexed.
```

- Takes under 2 minutes with Metal GPU
- Safe to re-run anytime — it upserts, doesn't duplicate
- Run this after adding significant new notes to your vault

---

## 3. Ask a question

```bash
uv run larvis ask "what are my active projects?"
```

**Good response (working):** Larvis lists real project names from your vault — jarvis-glowup, learn_go, ai_foundations, etc.

**Bad response (broken):**
- `"Vault not indexed"` → run `larvis reindex` first
- Hallucinated/generic answer with no vault content → reindex may be stale
- Long hang with no output → check `ollama list` and `docker compose ps`

Try other questions:
```bash
uv run larvis ask "what is my YNAB budget situation?"
uv run larvis ask "what are my goals for this year?"
uv run larvis ask "what did I work on this week?"
```

---

## 4. Search your vault directly

Returns raw matching chunks — useful to see exactly what context Larvis is working with.

```bash
uv run larvis search "budget" --top-k 3
```

Expected: 3 excerpts from your vault notes that contain budget-related content.

```bash
uv run larvis search "morning routine" --top-k 5
uv run larvis search "jarvis" --top-k 3
```

If search returns nothing relevant, the vault may need reindexing.

---

## 5. Quick sanity sequence (run this when in doubt)

```bash
# 1. Are the containers up?
docker compose ps

# 2. Is everything connected?
uv run larvis status

# 3. Is the vault indexed?
# (if index_docs is 0, run reindex)
uv run larvis reindex

# 4. Does it answer from vault context?
uv run larvis ask "what are my active projects?"
```

If all four pass, Larvis is working correctly.

---

## 6. Shut down cleanly

```bash
docker compose down
# Ollama: click the menu bar icon → Quit Ollama
```

Vault index (ChromaDB) is persisted in a Docker volume — you won't lose it on restart.

---

## 7. Restart after a reboot

```bash
open -a Ollama                    # start Ollama (or it may auto-start)
cd ~/repos/larvis
docker compose up -d              # start chromadb + larvis
uv run larvis status              # verify all green
```

No need to reindex after a restart — the index persists.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `ollama: false` in status | Ollama app not running | `open -a Ollama` |
| `chromadb: false` in status | Docker containers down | `docker compose up -d` |
| `index_docs: 0` | Vault not indexed | `uv run larvis reindex` |
| `ask` hangs forever | Ollama not responding | Check menu bar icon; `ollama list` |
| `ask` gives generic answer | Stale or empty index | `uv run larvis reindex` |
| Container crash on `docker compose up` | Colima low memory | `colima start --memory 10` then retry |
