import ollama

from larvis.config import settings


def _concat(blocks: dict[str, str]) -> str:
    return "\n\n".join(f"[{agent}]\n{text}" for agent, text in blocks.items())


def synthesize(query: str, blocks: dict[str, str]) -> str:
    context = _concat(blocks)
    try:
        resp = ollama.Client(host=settings.ollama_host).generate(
            model=settings.ollama_model,
            prompt=(
                "You are Larvis, a personal assistant. Answer the user's request using "
                "ONLY the agent results below. Be concise and direct; do not invent facts. "
                "If the results don't answer it, say so.\n\n"
                f"Agent results:\n{context}\n\nRequest: {query}"
            ),
        )
        return resp.response.strip()
    except Exception:
        return context
