from larvis.orchestrator import router


def test_route_single_agent():
    assert router.route("what's on my calendar today?") == ["calendar"]


def test_route_multiple_agents():
    agents = router.route("do I have time and budget for a date night?")
    assert "calendar" in agents and "ynab" in agents


def test_route_falls_back_to_lifeos():
    assert router.route("hello there") == ["lifeos"]


def test_is_write_intent_true():
    assert router.is_write_intent("add a chore for Cal") is True
    assert router.is_write_intent("remind me to call mom") is True


def test_is_write_intent_false():
    assert router.is_write_intent("what chores are left today?") is False


def test_detect_action_chore():
    assert router.detect_action("add trash chore to Cal")["tool"] == "skylight_add_chore"


def test_detect_action_commit():
    assert router.detect_action("remind me to book flights")["tool"] == "lifeos_commit"


def test_detect_action_unknown_returns_none():
    assert router.detect_action("create a spreadsheet") is None
