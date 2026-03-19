# gstack Review & Recommendations for basicSMTPAgenticComms

**Date:** 2026-03-19
**Reviewed repo:** [github.com/garrytan/gstack](https://github.com/garrytan/gstack)

---

## What is gstack?

gstack is an open-source "software factory" created by Garry Tan (YC CEO) that transforms Claude Code into a virtual engineering team. It delivers 15+ slash-command skills as Markdown files, covering the full development lifecycle from brainstorming to retrospective. Garry claims to have shipped 600K+ lines of production code in 60 days using this system.

### Key Innovation: Persistent Chromium Daemon

The standout technical contribution is a long-lived headless Chromium process that stays running across Claude Code commands:

- Traditional browser automation: ~3s cold start per command, state lost between calls
- gstack's approach: ~100ms per command after first call, full cookie/tab/localStorage persistence
- Uses accessibility-tree refs (`@e1`, `@e2`) instead of CSS selectors — works with React hydration, Shadow DOM, CSP
- Zero token overhead — plain text stdout, no JSON/MCP protocol framing

### The 15+ Skills (Full Lifecycle)

| Phase | Skill | Purpose |
|-------|-------|---------|
| Think | `/office-hours` | YC-style forcing questions before writing code |
| Plan | `/plan-ceo-review` | CEO/founder scope challenge |
| Plan | `/plan-eng-review` | Lock architecture, edge cases, test coverage |
| Plan | `/plan-design-review` | Rate design dimensions 0-10 |
| Plan | `/design-consultation` | Create complete design system from scratch |
| Build | `/browse` | Headless Chromium, ~100ms/cmd |
| Build | `/setup-browser-cookies` | Import real browser auth cookies |
| Review | `/review` | Staff engineer-level PR review |
| Review | `/design-review` | Visual QA with before/after screenshots |
| Review | `/codex` | OpenAI Codex second opinion |
| Test | `/qa` | Find bugs, fix, commit, re-verify loop |
| Test | `/qa-only` | Report-only bug assessment |
| Debug | `/investigate` | Root-cause debugging (no fixes without investigation) |
| Ship | `/ship` | Sync, test, bump version, PR, auto-docs |
| Docs | `/document-release` | Update all docs to match shipped code |
| Reflect | `/retro` | Weekly retro with per-person breakdowns |
| Safety | `/careful`, `/freeze`, `/guard` | Guardrails for prod/destructive operations |

### Core Design Principles

1. **"Boil the Lake"** — When AI makes completeness near-zero marginal cost, always do the complete thing rather than taking shortcuts
2. **Natural language logic** — Skill templates use English prose for conditionals, not shell if/elif
3. **Diff-scoped testing** — Only run tests/evals affected by `git diff`, not the full suite
4. **Session awareness** — When 3+ sessions run concurrently, every question re-grounds the user on project/branch/context
5. **Actionable errors** — All Playwright errors rewritten so Claude can self-recover without human help

---

## Our Project: basicSMTPAgenticComms

A Python reference implementation for agent-to-agent communication over email using Gmail's API. Clean architecture with four modules (config, email_transport, message, agent) but no tests, no CI/CD, no CLAUDE.md, and no development automation.

### Current Gaps

- No automated test suite
- No CI/CD pipeline
- No CLAUDE.md (Claude Code doesn't know our project conventions)
- No pre-commit hooks
- No logging framework (print statements only)
- No development documentation beyond README

---

## Recommendations: What to Adopt from gstack

### Priority 1: High Impact, Low Effort

#### 1. Create a CLAUDE.md

This is the single highest-ROI adoption from gstack. Every gstack skill reads project config from CLAUDE.md. For our repo, this means Claude Code would immediately know how to run, test, and lint the project without asking.

**Recommended content:**

```markdown
# CLAUDE.md - basicSMTPAgenticComms

## Project Overview
Agent-to-agent communication over email using Gmail API. Python 3.7+.

## Commands
- Install deps: `pip install -r requirements.txt`
- Run agent: `python main.py --email <gmail> --interval 30 --iterations 10`
- Run demo: `./initiate_simple_exchange_demo.sh`
- Run tests: `python -m pytest tests/ -v`  (once tests exist)
- Lint: `python -m flake8 src/`  (once configured)

## Architecture
- `src/config.py` - OAuth 2.0 authentication & config loading
- `src/email_transport.py` - Gmail API operations with label-based guaranteed delivery
- `src/message.py` - Message representation and serialization
- `src/agent.py` - Base Agent class with polling loop
- `main.py` - CLI entry point

## Conventions
- JSON payloads embedded in email bodies
- Per-agent token files: `{agent_name}_token.json`
- Label-based processing: "agent-processing" label for guaranteed delivery
- Messages use exchange-based schema with sender, timestamp, content

## Security
- Never commit token.json or credentials.json
- OAuth tokens are per-agent and stored locally
- credentials.json must be obtained from Google Cloud Console
```

#### 2. Adopt the "Boil the Lake" Principle

Add this to CLAUDE.md:

```
## Development Philosophy
When implementing changes, prefer completeness over shortcuts. If adding a feature,
include tests. If fixing a bug, add a regression test. The marginal cost of
completeness with AI assistance is near-zero.
```

This single prompt instruction changes Claude's behavior from "do the minimum" to "do it properly."

#### 3. Structured AskUserQuestion Pattern

gstack skills always re-ground context when asking questions. We can adopt this convention in our CLAUDE.md:

```
## When Asking Questions
Always include: which module is affected, what the current behavior is,
and what the proposed change would do. Recommend the most complete option first.
```

### Priority 2: Medium Effort, High Value

#### 4. Adopt the `/investigate` Pattern for Debugging

gstack's investigate skill enforces a strict rule: **no fixes without root cause analysis**. This is especially valuable for our project since email/API debugging can be tricky.

**Pattern to adopt in CLAUDE.md:**

```
## Debugging Protocol
When investigating bugs:
1. Reproduce the issue first
2. Form a hypothesis about root cause
3. Verify the hypothesis with evidence
4. Only then implement a fix
5. Add a test that would have caught the bug
Never apply speculative fixes without understanding the root cause.
```

#### 5. Add a Test Suite (gstack's `/qa` pattern)

gstack's QA skills demonstrate iterative test-fix-verify loops. We should bootstrap a test suite:

- Unit tests for `Message` serialization/deserialization
- Unit tests for `EmailTransport` with mocked Gmail API
- Integration test for the agent polling loop
- Test for the label-based guaranteed delivery workflow

This would make Claude Code vastly more effective — it can run tests to verify changes instead of guessing.

#### 6. Diff-Scoped Testing

Once tests exist, adopt gstack's principle of only running tests affected by changes. For our small codebase this means:

- Changes to `message.py` → run message tests
- Changes to `email_transport.py` → run transport tests
- Changes to `agent.py` → run agent tests
- Changes to `config.py` → run config tests

### Priority 3: Worth Considering Later

#### 7. Safety Guardrails (`/careful` pattern)

gstack's `/careful` and `/freeze` skills prevent destructive operations. For our project, relevant guardrails would be:

- Never commit or expose OAuth tokens
- Never send emails from the agent without user confirmation during development
- Warn before modifying `agent_config.json` in ways that could affect live agents

#### 8. Ship Workflow (`/ship` pattern)

Once we have tests and CI, adopt a structured ship workflow:
- Run tests → review diff → bump version → update changelog → push → create PR

#### 9. Document Release Pattern

gstack's `/document-release` automatically updates all docs after shipping code. Worth adopting once we have more documentation to maintain.

#### 10. Retro Pattern

gstack's `/retro` analyzes commit history and work patterns. Interesting for tracking progress on this project over time, but lower priority.

---

## What NOT to Adopt

| gstack Feature | Why Skip It |
|----------------|-------------|
| Persistent Chromium daemon | We don't have a web UI to test |
| Browser cookie import | No web frontend |
| Design review/consultation | No UI design work |
| Conductor (parallel sprints) | Overkill for our project size |
| Skill templating system | We don't have enough skills to justify |
| OpenAI Codex integration | Extra dependency, marginal value for our scope |
| Upgrade management system | We're not distributing a tool |

---

## Suggested Implementation Order

1. **Now:** Create CLAUDE.md with project conventions (30 min of Claude time)
2. **Next session:** Bootstrap pytest suite with mocked Gmail API tests
3. **Following session:** Add pre-commit hooks (lint, type check)
4. **When ready:** Set up CI/CD with GitHub Actions
5. **Ongoing:** Adopt debugging protocol and completeness principle

---

## Effort Compression Estimates (from gstack)

gstack tracks these ratios for AI-assisted development:

| Task Type | Human Time | Claude Code Time | Speedup |
|-----------|-----------|-------------------|---------|
| Boilerplate/scaffolding | Hours | Minutes | ~100x |
| Test writing | Hours | Minutes | ~50x |
| Feature implementation | Days | Hours | ~30x |
| Bug investigation | Hours | ~30 min | ~20x |
| Architecture decisions | Days | Hours | ~5x |

For our project, the biggest wins would be in **test writing** (we have zero tests) and **boilerplate** (config, CI/CD setup).

---

## Summary

gstack is impressive engineering optimized for high-volume solo shipping. For basicSMTPAgenticComms, the highest-value adoptions are:

1. **CLAUDE.md** — immediate, massive ROI
2. **"Boil the Lake" completeness principle** — changes Claude's default behavior
3. **Test suite bootstrapping** — enables the test-fix-verify loop that makes everything else work
4. **Debugging protocol** — prevents speculative fixes in email/API code
5. **Structured questions** — reduces back-and-forth in conversations

Everything else is either irrelevant to our stack (browser testing) or premature for our project size (parallel sprints, skill templating).
