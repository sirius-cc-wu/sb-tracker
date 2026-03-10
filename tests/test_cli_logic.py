import pytest
from sb_tracker import cli

def test_lifecycle_target_edge_cases():
    # pause
    assert cli._lifecycle_target("Doing", "pause", "Done") == "Ready"
    assert cli._lifecycle_target("Ready", "pause", "Done") is None
    
    # review
    assert cli._lifecycle_target("Doing", "review", "Done") == "Review"
    assert cli._lifecycle_target("Ready", "review", "Done") is None
    
    # finish
    assert cli._lifecycle_target("Review", "finish", "Done") == "Done"
    assert cli._lifecycle_target("Doing", "finish", "Done") == "Done"
    
    # invalid action
    assert cli._lifecycle_target("Doing", "unknown", "Done") is None

def test_lifecycle_target_needs_review():
    issue = {"needs_review": True}
    # Finish from Doing should move to Review
    assert cli._lifecycle_target("Doing", "finish", "Done", issue=issue) == "Review"
    # Finish from Review should move to Done
    assert cli._lifecycle_target("Review", "finish", "Done", issue=issue) == "Done"

def test_is_issue_done_edge_cases():
    db = {"meta": {"kanban": {"columns": ["Backlog", "Done"], "backlog": "Backlog", "done": "Done"}}}
    assert cli.is_issue_done({"status": "Done"}, db) is True
    assert cli.is_issue_done({"status": "Doing"}, db) is False
    
    # Custom config
    db_custom = {"meta": {"kanban_by_repo": {"/r": {"columns": ["Shipped"], "backlog": "Shipped", "done": "Shipped"}}}}
    assert cli.is_issue_done({"status": "Shipped", "repo": "/r"}, db_custom) is True
    assert cli.is_issue_done({"status": "Done", "repo": "/r"}, db_custom) is False

def test_normalize_status_mapping():
    cfg = {"columns": ["Todo", "Progress", "Done"], "backlog": "Todo", "done": "Done"}
    assert cli.normalize_status("open", cfg) == "Todo"
    assert cli.normalize_status("closed", cfg) == "Done"
    assert cli.normalize_status("Progress", cfg) == "Progress"
    assert cli.normalize_status("unknown", cfg) is None
