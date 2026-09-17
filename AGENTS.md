# ATLAS development collaboration

Use regular development sub-agents proactively for substantial ATLAS work when
bounded tasks can run independently alongside useful work by the main agent.
Choose assignments that help the actual task; small or tightly coupled changes
can stay with the main agent.

Useful development assignments include:

- **Implementation:** features, bug fixes and refactoring in a clearly owned
  component, such as an individual `components/desktop/plugins/atlas.*` plugin,
  application integration, CLI integration, or installer module.
- **Codebase exploration:** trace behavior, dependencies and compatibility before
  a change, and return relevant file references and a concise recommendation.
- **QA and regression testing:** behavior tests, installer/update/restoration
  checks, JavaScript models, CI and release packaging verification.
- **UI and performance review:** palette consistency, readability, layout and
  fractional scaling, animation behavior, polling and resource usage. Distinguish
  measured results from estimates and mocked checks from native validation.
- **Documentation and release review:** keep README, settings/help, validation
  notes and showcase claims consistent with implemented and tested behavior.

The main agent owns the overall design, user communication, integration and final
verification. Each delegated task must identify its objective, relevant context,
constraints, owned files and expected result. Tell workers they share the
codebase, must preserve others' changes, and must coordinate overlapping edits.
Continue useful independent work while agents run; avoid duplicate investigation.

Coordinate changes to `colors.toml`, `lib/atlas/palette.py`, shared templates and
their generated root theme files as one assignment. Give a plugin's JavaScript
model and corresponding behavior tests coordinated ownership. Reserve shared
integration files explicitly when multiple workers need them.

Keep affected tests and documentation aligned with the final implementation.
Run focused checks during development; use `python3 tools/check.py` for complete
Omarchy checks, or `--portable` for the documented headless subset. Release and
showcase entry points are `tools/check_release.py` and `tools/build_site.py`.
Follow `docs/VALIDATION.md` for dependencies and report remaining validation limits.
`dist/` is generated, and release packaging includes only tracked, explicitly
allowlisted files; account for new files without disturbing unrelated staging.

Ordinary development agents inherit the main agent's model/settings unless the
user or task-specific instructions specify otherwise. Use the separate security
agent preference for security-specific work, such as authentication boundaries,
privileged boot operations or installer path safety.
