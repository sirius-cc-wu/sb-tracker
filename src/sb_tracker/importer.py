import re

def parse_markdown_tasks(content: str):
    """
    Parses Markdown content and returns a list of task objects.
    Each task object contains 'title', 'level', and 'status'.
    """
    tasks = []
    lines = content.splitlines()

    for line in lines:
        # Match lines starting with - [ ] or * [ ] or - [x] or * [x]
        match = re.match(r"^(\s*)[-*]\s+\[([ xX])\]\s+(.*)", line)
        if match:
            indentation, checked, title = match.groups()
            
            # Determine indentation level
            # Assuming 2 spaces or 1 tab per level
            level = 0
            if '\t' in indentation:
                level = indentation.count('\t')
            else:
                level = len(indentation) // 2
            
            status = "done" if checked.lower() == "x" else "todo"
            
            tasks.append({
                "title": title.strip(),
                "level": level,
                "status": status
            })
            
    return tasks
