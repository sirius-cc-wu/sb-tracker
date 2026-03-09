import pytest
from sb_tracker import importer

def test_parse_flat_list():
    content = """
- [ ] Task 1
- [x] Task 2
* [ ] Task 3
"""
    tasks = importer.parse_markdown_tasks(content)
    assert len(tasks) == 3
    assert tasks[0] == {"title": "Task 1", "level": 0, "status": "todo"}
    assert tasks[1] == {"title": "Task 2", "level": 0, "status": "done"}
    assert tasks[2] == {"title": "Task 3", "level": 0, "status": "todo"}

def test_parse_nested_list():
    content = """
- [ ] Parent
  - [ ] Child 1
    - [ ] Grandchild
  - [ ] Child 2
"""
    tasks = importer.parse_markdown_tasks(content)
    assert len(tasks) == 4
    assert tasks[0]["title"] == "Parent" and tasks[0]["level"] == 0
    assert tasks[1]["title"] == "Child 1" and tasks[1]["level"] == 1
    assert tasks[2]["title"] == "Grandchild" and tasks[2]["level"] == 2
    assert tasks[3]["title"] == "Child 2" and tasks[3]["level"] == 1

def test_parse_mixed_content():
    content = """
# Header
Some text.

- [ ] Task 1
  * [x] Subtask
    Not a task line
- [ ] Task 2
"""
    tasks = importer.parse_markdown_tasks(content)
    assert len(tasks) == 3
    assert tasks[0]["title"] == "Task 1"
    assert tasks[1]["title"] == "Subtask" and tasks[1]["level"] == 1
    assert tasks[2]["title"] == "Task 2" and tasks[2]["level"] == 0

def test_parse_indentation_tabs():
    content = """
- [ ] Level 0
\t- [ ] Level 1
\t\t- [ ] Level 2
"""
    tasks = importer.parse_markdown_tasks(content)
    assert tasks[0]["level"] == 0
    assert tasks[1]["level"] == 1
    assert tasks[2]["level"] == 2

def test_empty_content():
    assert importer.parse_markdown_tasks("") == []
