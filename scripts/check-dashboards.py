#!/usr/bin/env python3
"""Static lint for the Grafana dashboards in infra/grafana/dashboards/.

Run by `make check-dashboards` (part of `make ci-static` and the CI `static`
job). For every dashboard JSON file it checks that:

- the file is valid JSON whose top level is an object;
- the dashboard has a non-empty string `uid`, and no two files share one;
- every datasource reference uses an allowed UID (`opencg-prometheus`,
  `opencg-tempo`, or Grafana's built-in `-- Grafana --` / `-- Dashboard --` /
  `-- Mixed --` pseudo-datasources, or a `${...}` template variable);
- every `opencg_*` metric named in a PromQL expression is defined by the
  shared metrics module (`opencg_shared.metrics`) or by the MCP server.
  `_total`, `_bucket`, `_count`, `_sum` and `_created` suffixes are handled.

The metric names are read by importing `opencg_shared.metrics` and
introspecting its Prometheus collectors, not hard-coded here, so a metric
added to the module is accepted with no change to this script.

When Docker is available it also runs `promtool check config` on
infra/prometheus/prometheus.yml through the pinned Prometheus image. Pass
`--no-promtool` to skip that, or set CHECK_DASHBOARDS_PROMTOOL=0.

Usage:
    uv run --package opencg-shared python scripts/check-dashboards.py [--no-promtool] [DIR]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DASHBOARD_DIR = ROOT / "infra" / "grafana" / "dashboards"
PROMETHEUS_CONFIG = ROOT / "infra" / "prometheus" / "prometheus.yml"
COMPOSE_OBSERVABILITY = ROOT / "infra" / "compose" / "docker-compose.observability.yml"

ALLOWED_DATASOURCE_UIDS = frozenset({"opencg-prometheus", "opencg-tempo"})
# Grafana's built-in pseudo-datasources (annotations, panel reuse, mixed).
BUILTIN_DATASOURCE_UIDS = frozenset({"grafana", "-- Grafana --", "-- Dashboard --", "-- Mixed --"})

# Families the MCP server (TypeScript, prom-client) exposes. They share their
# names with families in opencg_shared.metrics, but list them explicitly so the
# lint still accepts them if the Python module ever drops one.
MCP_SERVER_FAMILIES = {
    "opencg_requests_total": "counter",
    "opencg_stage_latency_seconds": "histogram",
}

SAMPLE_SUFFIXES = {
    "counter": ("_total", "_created"),
    "histogram": ("_bucket", "_count", "_sum", "_created"),
    "summary": ("_count", "_sum", "_created"),
    "gauge": ("",),
    "info": ("_info",),
    "stateset": ("",),
    "enum": ("",),
    "unknown": ("",),
}

METRIC_NAME_RE = re.compile(r"\bopencg_[A-Za-z0-9_]+")
# Keys whose string values hold PromQL in Grafana dashboard JSON.
EXPR_KEYS = frozenset({"expr", "query", "definition"})


def _family_base(family: str, mtype: str) -> str:
    if mtype == "counter" and family.endswith("_total"):
        return family[: -len("_total")]
    return family


def _sample_names(family: str, mtype: str) -> set[str]:
    """The sample names Prometheus exposes for a family of `mtype`."""
    base = _family_base(family, mtype)
    return {base + suffix for suffix in SAMPLE_SUFFIXES.get(mtype, ("",))}


def known_metric_names() -> set[str]:
    """Every sample name defined by opencg_shared.metrics plus the MCP server."""
    import opencg_shared.metrics as metrics_module
    from prometheus_client import CollectorRegistry
    from prometheus_client.metrics import MetricWrapperBase

    names: set[str] = set()
    # Counter and histogram families have no sample under their bare name, so
    # a query on one would always be empty; reject it.
    bare: set[str] = set()

    def add(family: str, mtype: str) -> None:
        names.update(_sample_names(family, mtype))
        if mtype in ("counter", "histogram", "summary"):
            bare.add(_family_base(family, mtype))

    registries: list[CollectorRegistry] = []
    for value in vars(metrics_module).values():
        if isinstance(value, MetricWrapperBase):
            add(value._name, getattr(value, "_type", "unknown"))
        elif isinstance(value, CollectorRegistry):
            registries.append(value)
        elif isinstance(value, dict):
            # Metrics kept in a dict (for example built per registry mode).
            for item in value.values():
                if isinstance(item, MetricWrapperBase):
                    add(item._name, getattr(item, "_type", "unknown"))
    for registry in registries:
        # Maps every exposed sample name (with suffixes) to its collector.
        names.update(getattr(registry, "_names_to_collectors", {}))
    for family, mtype in MCP_SERVER_FAMILIES.items():
        add(family, mtype)
    return {n for n in names - bare if n.startswith("opencg_")}


def _walk(node: object, path: str = "$") -> Iterator[tuple[str, str | None, object]]:
    """Yield (json_path, key, value) for every value in a JSON tree."""
    if isinstance(node, dict):
        for key, value in node.items():
            child = f"{path}.{key}"
            yield child, key, value
            yield from _walk(value, child)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            child = f"{path}[{index}]"
            yield child, None, value
            yield from _walk(value, child)


def _datasource_uids(node: object) -> Iterator[tuple[str, str]]:
    for path, key, value in _walk(node):
        if key != "datasource":
            continue
        if isinstance(value, dict):
            uid = value.get("uid")
            if uid is not None:
                yield path, str(uid)
        elif isinstance(value, str):
            # Legacy form: a datasource name or UID as a bare string.
            yield path, value


def _uid_allowed(uid: str) -> bool:
    if uid in ALLOWED_DATASOURCE_UIDS or uid in BUILTIN_DATASOURCE_UIDS:
        return True
    return uid.startswith("${") or uid.startswith("$")


def check_dashboard(path: Path, known: set[str]) -> list[str]:
    """Return a list of human-readable problems for one dashboard file."""
    errors: list[str] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        return [f"{path.name}: cannot read file: {exc}"]
    except json.JSONDecodeError as exc:
        return [f"{path.name}: invalid JSON: {exc}"]
    if not isinstance(data, dict):
        return [f"{path.name}: top level must be a JSON object"]

    uid = data.get("uid")
    if not isinstance(uid, str) or not uid.strip():
        errors.append(f"{path.name}: missing a stable `uid`")

    for json_path, ds_uid in _datasource_uids(data):
        if not _uid_allowed(ds_uid):
            errors.append(
                f"{path.name}: {json_path} references datasource UID {ds_uid!r}; "
                f"allowed: {', '.join(sorted(ALLOWED_DATASOURCE_UIDS))}"
            )

    for json_path, key, value in _walk(data):
        if key not in EXPR_KEYS or not isinstance(value, str):
            continue
        for name in sorted(set(METRIC_NAME_RE.findall(value))):
            if name not in known:
                errors.append(
                    f"{path.name}: {json_path} queries {name}, which "
                    "opencg_shared.metrics does not define"
                )
    return errors


def check_dashboards(paths: Iterable[Path], known: set[str]) -> list[str]:
    errors: list[str] = []
    seen_uids: dict[str, str] = {}
    for path in paths:
        errors.extend(check_dashboard(path, known))
        try:
            uid = json.loads(path.read_text(encoding="utf-8")).get("uid")
        except Exception:
            continue
        if isinstance(uid, str) and uid:
            if uid in seen_uids:
                errors.append(f"{path.name}: uid {uid!r} already used by {seen_uids[uid]}")
            seen_uids[uid] = path.name
    return errors


def _prometheus_image() -> str | None:
    if not COMPOSE_OBSERVABILITY.exists():
        return None
    match = re.search(r"image:\s*(prom/prometheus:\S+)", COMPOSE_OBSERVABILITY.read_text())
    return match.group(1) if match else None


def run_promtool() -> list[str]:
    """`promtool check config` via the pinned image; skipped without Docker."""
    image = _prometheus_image()
    if image is None:
        return ["cannot find the prom/prometheus image in docker-compose.observability.yml"]
    docker = shutil.which("docker")
    if (
        docker is None
        or subprocess.run([docker, "info"], capture_output=True, check=False).returncode
    ):
        print("promtool: skipped (Docker not available)")
        return []
    result = subprocess.run(
        [
            docker, "run", "--rm", "--entrypoint", "promtool",
            "-v", f"{PROMETHEUS_CONFIG.parent}:/etc/prometheus:ro",
            image, "check", "config", "/etc/prometheus/prometheus.yml",
        ],
        capture_output=True,
        text=True,
        check=False,
    )  # fmt: skip
    if result.returncode:
        return [f"promtool check config failed:\n{result.stdout}{result.stderr}"]
    print(f"promtool: {PROMETHEUS_CONFIG.relative_to(ROOT)} is valid ({image})")
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("directory", nargs="?", type=Path, default=DEFAULT_DASHBOARD_DIR)
    parser.add_argument("--no-promtool", action="store_true", help="skip promtool check config")
    args = parser.parse_args(argv)

    files = sorted(args.directory.glob("*.json"))
    if not files:
        print(f"no dashboard files found in {args.directory}", file=sys.stderr)
        return 1

    errors = check_dashboards(files, known_metric_names())
    if not args.no_promtool and os.environ.get("CHECK_DASHBOARDS_PROMTOOL", "1") != "0":
        errors.extend(run_promtool())

    if errors:
        for error in errors:
            print(f"✗ {error}", file=sys.stderr)
        print(f"{len(errors)} problem(s) in {args.directory}", file=sys.stderr)
        return 1
    print(f"✓ {len(files)} dashboard(s) in {args.directory} pass the lint")
    return 0


if __name__ == "__main__":
    sys.exit(main())
