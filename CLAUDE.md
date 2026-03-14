# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**The Agency** is a curated collection of 80+ specialized AI agent prompt files organized by division. Each agent is a Markdown file with YAML frontmatter (`name`, `description`, `color`) defining a personality, workflows, deliverables, and success metrics. This is a content-only repo — no application code.

## Repository Structure

```
design/              # UX/UI and creative agents
engineering/         # Software development agents
game-development/    # Unity, Unreal, Godot, Roblox agents
  unity/
  unreal-engine/
  godot/
  roblox-studio/
marketing/           # Growth and marketing agents
paid-media/          # Paid media agents (referenced in CI/scripts, may not exist yet)
product/             # Product management agents
project-management/  # PM and coordination agents
testing/             # QA and testing agents
support/             # Operations and support agents
spatial-computing/   # AR/VR/XR agents
specialized/         # Unique cross-functional agents
strategy/            # Strategy agents
examples/            # Multi-agent workflow examples
integrations/        # Tool-specific conversion output (Cursor, Aider, Windsurf, etc.)
scripts/             # convert.sh, install.sh, lint-agents.sh
```

## Agent File Format

Every agent `.md` file must have YAML frontmatter with three required fields:

```markdown
---
name: Agent Name
description: One-line description
color: colorname or "#hexcode"
---
```

Followed by sections: Identity & Memory, Core Mission, Critical Rules, Technical Deliverables, Workflow Process, Communication Style, Learning & Memory, Success Metrics. The linter warns (but does not fail) on missing recommended sections: Identity, Core Mission, Critical Rules.

## Key Commands

- `./scripts/lint-agents.sh [files...]` — validate frontmatter and structure; with no args, scans all agent directories. Errors on missing frontmatter fields, warns on missing sections or short bodies (<50 words).
- `./scripts/convert.sh [--tool <name>] [--out <dir>]` — generate integration files for supported tools (antigravity, gemini-cli, opencode, cursor, aider, windsurf, or `all`). Output goes to `integrations/<tool>/`.
- `./scripts/install.sh [--tool <name>] [--interactive|--no-interactive]` — install agents into local tool config directories. Claude Code and Copilot install directly from source `.md` files; other tools require running `convert.sh` first.

## CI

GitHub Actions workflow (`.github/workflows/lint-agents.yml`) runs `lint-agents.sh` on PRs that touch agent directories.

## Conventions

- Agent filenames follow the pattern `<division>-<agent-name>.md` (e.g., `engineering-frontend-developer.md`)
- Game development agents are further nested by engine subdirectory
- New agents go in the appropriate division directory; use `specialized/` if none fits
- All agent content is Markdown with emoji section headers
- No application code — this repo is purely prompt/agent definitions and shell scripts
