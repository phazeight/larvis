from pathlib import Path
import pytest
from larvis.agents.lifeos.linear_sync import scan_vault_for_tagged_tasks


def test_scan_extracts_unchecked_to_linear_tasks(tmp_path):
    note = tmp_path / "todo.md"
    note.write_text(
        "# Tasks\n\n"
        "- [ ] Fix the dishwasher #to-linear\n"
        "- [ ] Normal task\n"
        "- [x] Already done #to-linear\n"
    )
    tasks = scan_vault_for_tagged_tasks(tmp_path)
    assert len(tasks) == 1
    assert tasks[0]["task_text"] == "Fix the dishwasher"
    assert tasks[0]["vault_file"] == "todo.md"


def test_scan_strips_tag_from_task_text(tmp_path):
    note = tmp_path / "note.md"
    note.write_text("- [ ] Buy groceries #to-linear\n")
    tasks = scan_vault_for_tagged_tasks(tmp_path)
    assert tasks[0]["task_text"] == "Buy groceries"


def test_scan_ignores_checked_tasks(tmp_path):
    note = tmp_path / "note.md"
    note.write_text("- [x] Already done #to-linear\n")
    tasks = scan_vault_for_tagged_tasks(tmp_path)
    assert len(tasks) == 0


def test_scan_finds_tasks_in_nested_files(tmp_path):
    subdir = tmp_path / "projects" / "myproject"
    subdir.mkdir(parents=True)
    note = subdir / "tasks.md"
    note.write_text("- [ ] Deploy the server #to-linear\n")
    tasks = scan_vault_for_tagged_tasks(tmp_path)
    assert len(tasks) == 1
    assert tasks[0]["vault_file"] == "projects/myproject/tasks.md"


def test_scan_returns_empty_for_vault_with_no_tagged_tasks(tmp_path):
    note = tmp_path / "note.md"
    note.write_text("- [ ] Just a normal task\n")
    tasks = scan_vault_for_tagged_tasks(tmp_path)
    assert len(tasks) == 0
