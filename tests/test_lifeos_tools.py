from larvis.agents.lifeos import tools


def test_find_overdue_tasks_flags_past_due_only(tmp_path):
    note = tmp_path / "daily.md"
    note.write_text(
        "- [ ] test overdue task 📅 2026-06-11\n"
        "- [ ] future task 📅 2099-01-01\n"
        "- [ ] no date task\n"
        "- [x] already done 📅 2000-01-01\n",
        encoding="utf-8",
    )
    overdue = tools.find_overdue_tasks(tmp_path, "2026-06-12")
    texts = [o["text"] for o in overdue]
    assert any("test overdue task" in t for t in texts)
    assert not any("future task" in t for t in texts)   # not yet due
    assert not any("no date task" in t for t in texts)  # no due date
    assert not any("already done" in t for t in texts)  # checked tasks ignored


def test_find_overdue_tasks_reports_due_date(tmp_path):
    (tmp_path / "n.md").write_text("- [ ] pay bill 📅 2026-01-05\n", encoding="utf-8")
    overdue = tools.find_overdue_tasks(tmp_path, "2026-06-12")
    assert overdue[0]["due"] == "2026-01-05"


def test_find_overdue_tasks_sorted_most_recent_due_first(tmp_path):
    (tmp_path / "n.md").write_text(
        "- [ ] old one 📅 2026-04-06\n"
        "- [ ] recent one 📅 2026-06-11\n"
        "- [ ] middle one 📅 2026-05-01\n",
        encoding="utf-8",
    )
    overdue = tools.find_overdue_tasks(tmp_path, "2026-06-12")
    assert [o["due"] for o in overdue] == ["2026-06-11", "2026-05-01", "2026-04-06"]
