# Changelog

All notable changes to CSB are documented here.

## Unreleased

### Added
- New `csb cleanup` command for managing disk usage:
  - Interactive cleanup with dry-run preview
  - Finds and removes stopped CSB containers
  - Finds and removes unused CSB images (`vsc-*` pattern)
  - Detects orphaned `.devcontainer/` directories
  - Prunes dangling Docker images
  - JSON output for scripting (`csb cleanup report --json`)
  - Subcommands for targeted cleanup: `containers`, `images`, `orphans`, `dangling`

## 0.1.1 - 2026-01-01
- Fix: avoid stop hook errors when absolute-path commands point to missing binaries.
- Add: generate runtime MCP config and container-safe settings overlays for devcontainer mounts.
- Update: standardize runtime MCP mounts and workspace layout in the devcontainer.
