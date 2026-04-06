# deepin-agent-teams RFC

## Project Overview

**Name**: deepin-agent-teams
**Task**: Hackathon #27 - Deepin x Baidu ERNIE Multi-Agent System
**Goal**: On deepin 25, implement a multi-agent collaboration system using OpenClaw + ERNIE Bot API

## Architecture Evolution

### v1 (deprecated) - Fake Multi-Agent
- Three Python classes, serial LLM call chain
- Problem: no real agent isolation

### v2 (multi-process) - Fixed Division
- Orchestrator spawns independent subprocess workers
- Fixed: researcher reads files / coder analyzes code
- Problem: division hardcoded, hard to extend

### v3 (extensible) - Registry-driven
- AgentRegistry: capability registration center + task queue
- fcntl.flock for concurrent-safe file locking
- Workers autonomously claim tasks from Registry
- Capabilities: Python-implemented functions (file_reader/dir_scanner/etc)

### v4 (sessions_spawn) - OpenClaw Native (Current)
- sessions_spawn creates real OpenClaw sub-agents
- Sub-agents have native OpenClaw tools: read, exec, web_fetch
- Have LLM reasoning and system prompt context

```
Orchestrator (OpenClaw Agent)
    ↓ sessions_spawn
    ├── Researcher → OpenClaw tools: read, web_fetch, search
    ├── Coder → OpenClaw tools: read, exec
    └── General → OpenClaw tools: read, exec, write
    ↓ sessions_send
    Sub-agents execute and return Markdown reports
```

## Verification Record

### sessions_spawn Demo (2026-04-06)
- main Agent spawned 2 sub-agents (Researcher + Coder)
- sessions_spawn successfully returned childSessionKey
- sessions_send dispatched tasks and got Markdown reports
- Researcher returned: project structure analysis
- Coder returned: deep code analysis (classes/functions/dependencies)
- Status: Fully passed

## Code Structure

```
deepin-agent-teams/
├── main.py                          # CLI entry
├── config.py                        # Configuration
├── agents/
│   ├── base.py                      # Agent base class (erniebot)
│   ├── lead.py                     # Lead Agent
│   ├── researcher.py                # Researcher Agent
│   ├── coder.py                   # Coder Agent
│   ├── registry.py                # Agent Registry (v3)
│   ├── orchestrator.py           # Multi-process Orchestrator (v2)
│   ├── orchestrator_extensible.py # Extensible Orchestrator (v3)
│   ├── sessions_orchestrator.py  # Sessions-Spawn Orchestrator (v4)
│   ├── worker_v2.py             # Extensible Worker (v3)
│   ├── worker_researcher.py      # Researcher subprocess (v2)
│   └── worker_coder.py          # Coder subprocess (v2)
└── scenarios/
    ├── code_analysis.py        # Scenario 1
    └── literature_review.py     # Scenario 2
```

## Progress

| Phase | Time | Status |
|-------|------|--------|
| Week 1: Setup + Framework | 4/1-4/7 | Done |
| Week 2: Lead + Researcher | 4/8-4/14 | Done |
| Week 3: Coder + Scenario 1 | 4/15-4/21 | Done |
| Week 4: Architecture Refactor | 4/22-4/28 | Done |
| Week 5: sessions_spawn v4 | 4/29-5/5 | Done |
