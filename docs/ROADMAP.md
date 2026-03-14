# SB Tracker Roadmap: The Agentic Development Harness

This document outlines the strategic direction for `sb-tracker` to become the definitive "harness" for autonomous, long-horizon development agents, as inspired by OpenAI's research.

## Current State (v0.7.0)
- [x] **Durable Project Memory**: SQLite-backed persistent state.
- [x] **Task Hierarchy**: Tree-view visualization.
- [x] **Plan Ingestion**: `sb import` command for Markdown plans.
- [x] **Verification Loop**: `sb verify` command for automated feedback.

## Phase 1: Context Hydration (Completed)
Goal: Minimize "Discovery" phase turns and token costs.

- [x] **`sb context <id>`**:
    - Generates a single-shot "Context Hydration" block for agents.
    - Includes task spec, linked file summaries, and the last `sb verify` failure.
- [x] **Enhanced `sb link`**:
    - Associate specific file paths with a task.
    - Use `sb link <id> file=src/main.py`.

## Phase 2: Visibility & Governance (Medium Term)
Goal: Align with Git-based workflows and enforce quality.

- [ ] **`sb doc` (Living History)**:
    - Sync the SQLite audit log to a version-controlled `PROJECT_LOG.md`.
    - Automatically generate "Human-Readable" summaries of work completed.
- [ ] **`.sb/config.json` (Architectural Guardrails)**:
    - Define project-level "Definition of Done" requirements.
    - Example: `sb finish` blocks unless `lint` and `test` verifications have passed.

## Phase 3: Autonomous Handoff (Long Term)
Goal: Seamless transitions between different agents and humans.

- [ ] **`sb handoff`**:
    - Package the current task state, environment diffs, and verification logs into a "Handoff Bundle."
    - Allows a new agent session to resume with zero context loss.
- [ ] **Telemetry Integration**:
    - Ingest live logs or CI results directly into the task context.

## Design Pillars
1. **Tool-Centricity**: Commands should return outputs optimized for LLM parsing.
2. **Persistence > Prompts**: Context lives in the harness, not just the chat history.
3. **Rigidity is Safety**: Use verification to prevent "spaghetti implementation."
