---
name: align-repository
description: >-
  Reports the proposed changes that would make this repository meet the
  standards in AGENTS.md, including compact-python formatting and one file
  per class or dataclass that has functions. Use when the user runs
  /align-repository or asks to align the repository, bring the repo up to
  its standards, or report the changes that would match its conventions.
---

# Align repository

Write a report of the proposed changes that would make this repository satisfy `AGENTS.md`, and file it at the path under Report. That report is the whole task. `AGENTS.md`, `AGENTS.override.md`, and the skills those files name are the standards. Read them. Do not copy those standards into this skill or into a second checklist.

Work from the repository that contains this skill.

## Target repositories

The valid target repositories are:

- `springs-of-mud-ui`
- `springs-of-mud-server`
- `springs-of-mud-designer`
- `som-server-modulith`

## Find the gaps

Read `AGENTS.md` and `AGENTS.override.md` at the repo root. Include every section. Read each file cited in the Reference section and treat it as part of the standards. When a convention names a skill, read that skill. Python formatting is `.grok/skills/compact-python/SKILL.md`. When a standard requires a collection change, name the collection skill that owns that work.

Compare `src/` and `tests/` with those standards. Skip virtual environments, `site-packages`, and `__pycache__`. Record each gap for the report. Use Coding Conventions for which class or dataclass belongs in its own file. A gap also includes code that sits in a package `AGENTS.md` assigns elsewhere, and formatting the compact-python skill would still collapse.

A proposal preserves behavior except where a standard requires a move or a file rename. For a type the standard gives its own file, record the type, the PascalCase path, the module-level helpers that exist to serve that type, and each importer. If a package `__init__` already exports the name, record that the export would point at the new module. If keeping an existing lazy import would still leave an import cycle, record that the cycle blocks the move.

Record a formatting proposal after any move that touches the same file.

Also compare boundary naming, registries, where sockets live, logging, and telnet negotiation. When a proposed move changes a path that the Testing reference tells the operator to run, record that path update in `docs/reference/Testing.md` as its own proposed change. Proposals leave product rules unchanged.

Propose a change to `resources/agent.yml`, `resources/connections.json`, or a collection document only when a standard requires that change. Omit passwords, JWTs, and `Authorization` headers from the report.

## Report

File the report in `docs/alignment`. Create the folder when it is missing. Name the file with the target repository from Target repositories and the local time it is filed, in 24-hour form: `<repository>_<YYYY-MM-DDTHHMMSS>.md`.

For each recorded gap, name the file, the standard it addresses, and the proposed change, including any move, importer, and cycle notes. If the comparison finds no gap, say there is nothing to propose. If a gap cannot be stated precisely, name the file and what is still unknown.
