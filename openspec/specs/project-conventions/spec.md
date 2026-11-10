# project-conventions Specification

## Purpose

Fix the project's canonical name, identifiers and namespaces (Open Context Graph, openCG, `opencg`), so code, configuration, packages and docs use them consistently.

## Requirements
### Requirement: Canonical project naming and namespaces

The project SHALL be named **Open Context Graph** (short form **openCG**, slug `opencg`) and all identifiers, namespaces, configuration keys, telemetry names, and documentation SHALL use the openCG naming scheme consistently. No "Cortex" or "Hive Mind" identifier SHALL remain in active (non-archived) source, configuration, or documentation.

#### Scenario: Namespaces use the openCG scheme

- **WHEN** a package, module, or workspace member is referenced
- **THEN** TypeScript packages use the `@opencg/*` scope and Python packages use the `opencg_*` prefix (e.g. `@opencg/admin-ui`, `opencg_pipeline`)

#### Scenario: Configuration and telemetry use the openCG scheme

- **WHEN** an environment variable, Postgres schema, or Prometheus metric is referenced
- **THEN** environment variables use the `OPENCG__*` prefix, the database schema is `opencg`, and metric names use the `opencg_*` prefix

#### Scenario: MCP surface uses the openCG scheme

- **WHEN** the MCP server advertises itself or its tools
- **THEN** the server name is `opencg` and tools are namespaced `opencg/<tool>` (e.g. `opencg/retrieve_for_context`)

#### Scenario: No legacy name remains in active sources

- **WHEN** the tracked, non-archived files are searched case-insensitively for `cortex` or `hive[-_ ]?mind`
- **THEN** no matches are found, except within `openspec/changes/archive/**` historical records

