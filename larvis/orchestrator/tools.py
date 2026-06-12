from larvis.orchestrator import adapters, pending, router, synthesize


def _describe(tool: str, params: dict) -> str:
    if tool == "skylight_add_chore":
        return f'add chore "{params.get("summary")}" to {params.get("member")} ({params.get("when")})'
    if tool == "lifeos_commit":
        return f'commit: "{params.get("text")}"'
    return tool


def orchestrate(query: str, session_id: str = "orchestrator") -> str:
    if router.is_write_intent(query):
        action = router.detect_action(query)
        if not action:
            return "That looks like an action, but I don't have a tool for it yet."
        try:
            params = adapters.extract_params(action, query)
        except ValueError:
            fields = ", ".join(action["fields"])
            return (
                f"I think you want to {action['tool']}, but couldn't parse the details — "
                f"please be explicit about {fields}."
            )
        token = pending.propose({"tool": action["tool"], "params": params})
        return f'Proposed: {_describe(action["tool"], params)}.\nConfirm with larvis_confirm("{token}").'

    agents = router.route(query)
    blocks = adapters.gather(agents, query, session_id)
    return synthesize.synthesize(query, blocks)


def confirm(token: str) -> str:
    return pending.execute(token, adapters.WRITE_TOOLS)
