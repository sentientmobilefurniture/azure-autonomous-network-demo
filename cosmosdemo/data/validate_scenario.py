#!/usr/bin/env python3
"""
Validate a scenario's cross-reference integrity.

Checks that all IDs, file references, and schema definitions are consistent
across CSVs, graph_schema.yaml, scenario.yaml, telemetry, and tickets.

Usage:
    python3 data/validate_scenario.py <scenario-name>
    python3 data/validate_scenario.py telco-noc

Exit code 0 = all checks pass.
Exit code 1 = one or more checks failed.
"""

import csv
import os
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML not installed. Run: pip install pyyaml")
    sys.exit(2)


# ── Colour helpers ────────────────────────────────────────────────────────────

GREEN = "\033[0;32m"
RED = "\033[0;31m"
YELLOW = "\033[0;33m"
BOLD = "\033[1m"
NC = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}✓{NC} {msg}")


def fail(msg: str) -> None:
    print(f"  {RED}✗{NC} {msg}")


def warn(msg: str) -> None:
    print(f"  {YELLOW}⚠{NC} {msg}")


# ── CSV helpers ───────────────────────────────────────────────────────────────


def read_csv_file(path: Path) -> tuple[list[str], list[dict]]:
    """Return (headers, rows_as_dicts) from a CSV file."""
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        rows = list(reader)
    return list(headers), rows


def collect_entity_ids(entities_dir: Path) -> dict[str, set[str]]:
    """Collect all entity IDs from Dim*.csv files, keyed by filename."""
    result: dict[str, set[str]] = {}
    if not entities_dir.is_dir():
        return result
    for csv_file in sorted(entities_dir.glob("Dim*.csv")):
        headers, rows = read_csv_file(csv_file)
        # ID column is typically the first column
        id_col = headers[0] if headers else None
        if id_col:
            result[csv_file.name] = {row[id_col] for row in rows if row.get(id_col)}
    return result


def all_vertex_ids(entity_ids: dict[str, set[str]]) -> set[str]:
    """Flatten all entity IDs into one set."""
    ids: set[str] = set()
    for s in entity_ids.values():
        ids |= s
    return ids


# ── Validators ────────────────────────────────────────────────────────────────


def validate_scenario_yaml(scenario_dir: Path) -> tuple[dict, list[str]]:
    """Validate scenario.yaml exists and has required fields."""
    errors: list[str] = []
    scenario_path = scenario_dir / "scenario.yaml"

    if not scenario_path.exists():
        errors.append("scenario.yaml not found")
        return {}, errors

    with open(scenario_path) as f:
        data = yaml.safe_load(f)

    required_top = ["name", "display_name", "description", "version", "domain"]
    for field in required_top:
        if field not in data:
            errors.append(f"scenario.yaml missing required field: {field}")

    if "paths" not in data:
        errors.append("scenario.yaml missing 'paths' section")
    else:
        for p in ["entities", "graph_schema", "telemetry", "prompts"]:
            if p not in data["paths"]:
                errors.append(f"scenario.yaml paths.{p} missing")

    if "data_sources" not in data:
        errors.append("scenario.yaml missing 'data_sources' section")
    else:
        ds = data["data_sources"]
        if "graph" not in ds:
            errors.append("scenario.yaml missing data_sources.graph")
        if "telemetry" not in ds:
            errors.append("scenario.yaml missing data_sources.telemetry")

    if "agents" not in data:
        errors.append("scenario.yaml missing 'agents' section")
    elif data.get("agents"):
        roles = {a.get("role") for a in data["agents"]}
        if "orchestrator" not in roles:
            errors.append("scenario.yaml agents missing required role: orchestrator")
        if len(data["agents"]) < 2:
            errors.append("scenario.yaml should define at least 2 agents (1 orchestrator + sub-agents)")

    if "graph_styles" not in data:
        errors.append("scenario.yaml missing 'graph_styles' section")

    return data, errors


def validate_graph_schema(
    scenario_dir: Path,
    entity_ids: dict[str, set[str]],
) -> list[str]:
    """Validate graph_schema.yaml against CSV files."""
    errors: list[str] = []
    schema_path = scenario_dir / "graph_schema.yaml"

    if not schema_path.exists():
        errors.append("graph_schema.yaml not found")
        return errors

    with open(schema_path) as f:
        schema = yaml.safe_load(f)

    data_dir = scenario_dir / schema.get("data_dir", "data/entities")
    vertex_labels: set[str] = set()
    vertex_id_props: dict[str, str] = {}  # label → id_column

    # ── Vertex checks ─────────────────────────────────────────────────────
    for v in schema.get("vertices", []):
        label = v.get("label", "?")
        vertex_labels.add(label)
        csv_file = v.get("csv_file", "")
        id_col = v.get("id_column", "")
        props = v.get("properties", [])
        vertex_id_props[label] = id_col

        csv_path = data_dir / csv_file
        if not csv_path.exists():
            errors.append(f"graph_schema vertex '{label}': csv_file '{csv_file}' not found in {data_dir}")
            continue

        headers, _ = read_csv_file(csv_path)

        if id_col not in headers:
            errors.append(f"graph_schema vertex '{label}': id_column '{id_col}' not in CSV headers {headers}")

        for prop in props:
            if prop not in headers:
                errors.append(f"graph_schema vertex '{label}': property '{prop}' not in CSV headers {headers}")

        if not v.get("partition_key"):
            errors.append(f"graph_schema vertex '{label}': missing partition_key")

    # ── Edge checks ───────────────────────────────────────────────────────
    for i, e in enumerate(schema.get("edges", [])):
        edge_label = e.get("label", f"edge_{i}")
        csv_file = e.get("csv_file", "")
        csv_path = data_dir / csv_file

        if not csv_path.exists():
            errors.append(f"graph_schema edge '{edge_label}': csv_file '{csv_file}' not found")
            continue

        headers, _ = read_csv_file(csv_path)

        for endpoint in ["source", "target"]:
            ep = e.get(endpoint, {})
            ep_label = ep.get("label", "?")
            ep_col = ep.get("column", "?")

            if ep_label not in vertex_labels:
                errors.append(
                    f"graph_schema edge '{edge_label}' {endpoint}.label '{ep_label}' "
                    f"doesn't match any vertex label"
                )
            if ep_col not in headers:
                errors.append(
                    f"graph_schema edge '{edge_label}' {endpoint}.column '{ep_col}' "
                    f"not in CSV headers of {csv_file}"
                )

        # Filter column check
        filt = e.get("filter")
        if filt:
            if filt.get("column") and filt["column"] not in headers:
                errors.append(
                    f"graph_schema edge '{edge_label}' filter.column "
                    f"'{filt['column']}' not in CSV headers of {csv_file}"
                )

    return errors


def validate_telemetry(
    scenario_dir: Path,
    scenario_data: dict,
    all_ids: set[str],
    vertex_labels: set[str],
) -> list[str]:
    """Validate telemetry CSVs against entity IDs."""
    errors: list[str] = []

    telemetry_dir = scenario_dir / scenario_data.get("paths", {}).get("telemetry", "data/telemetry")
    if not telemetry_dir.is_dir():
        errors.append(f"Telemetry directory not found: {telemetry_dir}")
        return errors

    # Check AlertStream.csv exists
    alert_csv = telemetry_dir / "AlertStream.csv"
    if not alert_csv.exists():
        errors.append("AlertStream.csv not found in telemetry directory")
        return errors

    headers, rows = read_csv_file(alert_csv)

    # Check required columns
    required_cols = ["AlertId", "Timestamp", "SourceNodeId", "SourceNodeType", "AlertType", "Severity"]
    for col in required_cols:
        if col not in headers:
            errors.append(f"AlertStream.csv missing required column: {col}")

    if "SourceNodeId" not in headers or "SourceNodeType" not in headers:
        return errors

    # Check entity ID cross-references
    unknown_ids: set[str] = set()
    unknown_types: set[str] = set()
    null_count = 0

    # Identify numeric columns (everything after the descriptive columns)
    numeric_cols = [h for h in headers if h not in required_cols and h != "Description"]

    for row in rows:
        node_id = row.get("SourceNodeId", "")
        node_type = row.get("SourceNodeType", "")

        if node_id and node_id not in all_ids:
            unknown_ids.add(node_id)
        if node_type and node_type not in vertex_labels:
            unknown_types.add(node_type)

        # Check no-null rule on numeric columns
        for col in numeric_cols:
            val = row.get(col, "")
            if val is None or val.strip() == "":
                null_count += 1

    if unknown_ids:
        sample = sorted(unknown_ids)[:5]
        errors.append(
            f"AlertStream.csv has {len(unknown_ids)} SourceNodeId(s) not in entity CSVs: "
            f"{sample}{'...' if len(unknown_ids) > 5 else ''}"
        )

    if unknown_types:
        errors.append(
            f"AlertStream.csv has SourceNodeType(s) not matching vertex labels: "
            f"{sorted(unknown_types)}"
        )

    if null_count > 0:
        errors.append(
            f"AlertStream.csv has {null_count} null/empty numeric values "
            f"(violates no-null rule)"
        )

    # Check scenario.yaml telemetry containers match CSV files
    ds = scenario_data.get("data_sources", {})
    telemetry_ds = ds.get("telemetry", {})
    containers = telemetry_ds.get("config", {}).get("containers", [])
    for container in containers:
        csv_name = container.get("csv_file", "")
        if csv_name and not (telemetry_dir / csv_name).exists():
            errors.append(
                f"scenario.yaml telemetry container '{container.get('name')}' "
                f"references csv_file '{csv_name}' which doesn't exist"
            )

    return errors


def validate_junction_tables(
    entities_dir: Path,
    all_ids: set[str],
) -> list[str]:
    """Validate Fact*.csv junction tables reference valid entity IDs."""
    errors: list[str] = []

    if not entities_dir.is_dir():
        return errors

    for fact_csv in sorted(entities_dir.glob("Fact*.csv")):
        headers, rows = read_csv_file(fact_csv)
        # Check columns that look like ID references
        id_columns = [h for h in headers if h.endswith("Id") and h not in ("HopOrder",)]
        for col in id_columns:
            missing: set[str] = set()
            for row in rows:
                val = row.get(col, "")
                if val and val not in all_ids:
                    missing.add(val)
            if missing:
                sample = sorted(missing)[:5]
                errors.append(
                    f"{fact_csv.name} column '{col}' has {len(missing)} ID(s) "
                    f"not found in Dim*.csv: {sample}"
                )

    return errors


def validate_tickets(
    scenario_dir: Path,
    scenario_data: dict,
    all_ids: set[str],
) -> list[str]:
    """Validate ticket files reference valid entity IDs."""
    errors: list[str] = []

    tickets_dir = scenario_dir / scenario_data.get("paths", {}).get("tickets", "data/knowledge/tickets")
    if not tickets_dir.is_dir():
        warn("No tickets directory found — skipping ticket validation")
        return errors

    ticket_files = list(tickets_dir.glob("*.txt"))
    if not ticket_files:
        errors.append("No ticket .txt files found in tickets directory")
        return errors

    if len(ticket_files) < 8:
        warn(f"Only {len(ticket_files)} tickets found (guideline: 8–12)")

    root_cause_pattern = re.compile(r"^Root Cause:\s*(.+)$", re.MULTILINE)
    impact_pattern = re.compile(r"^- (.+)$", re.MULTILINE)

    for ticket_path in ticket_files:
        content = ticket_path.read_text()
        # Check root cause references a real entity ID
        rc_match = root_cause_pattern.search(content)
        if rc_match:
            rc_id = rc_match.group(1).strip()
            if rc_id not in all_ids:
                errors.append(
                    f"Ticket {ticket_path.name}: Root Cause '{rc_id}' "
                    f"not found in entity CSVs"
                )

        # Check customer impact IDs
        # Find the Customer Impact section
        impact_start = content.find("Customer Impact:")
        if impact_start >= 0:
            impact_section = content[impact_start:]
            # End at next section (line not starting with -)
            for line in impact_section.split("\n")[1:]:
                line = line.strip()
                if line.startswith("- "):
                    entity_id = line[2:].strip()
                    if entity_id and entity_id != "(None)" and entity_id not in all_ids:
                        errors.append(
                            f"Ticket {ticket_path.name}: Customer Impact "
                            f"'{entity_id}' not found in entity CSVs"
                        )
                elif line and not line.startswith("-"):
                    break  # End of impact list

    return errors


def validate_prompts(
    scenario_dir: Path,
    scenario_data: dict,
) -> list[str]:
    """Validate prompt fragments exist and X-Graph rule is present."""
    errors: list[str] = []

    prompts_dir = scenario_dir / scenario_data.get("paths", {}).get("prompts", "data/prompts")
    if not prompts_dir.is_dir():
        errors.append(f"Prompts directory not found: {prompts_dir}")
        return errors

    scenario_name = scenario_data.get("name", "")
    graph_name = f"{scenario_name}-topology"

    # Derive agent prompt files from scenario.yaml instructions_file fields.
    # These paths are relative to the scenario's data/ directory
    # (e.g. "prompts/foundry_x.md" → scenario_dir/data/prompts/foundry_x.md).
    data_dir = scenario_dir / "data"
    for agent in scenario_data.get("agents", []):
        ifile = agent.get("instructions_file", "")
        if ifile:
            # instructions_file can be a directory (graph_explorer/) or a file
            p = data_dir / ifile
            if ifile.endswith("/"):
                if not p.is_dir():
                    errors.append(f"Agent '{agent.get('name', '?')}' instructions_file directory missing: {ifile}")
            else:
                if not p.exists():
                    errors.append(f"Agent '{agent.get('name', '?')}' instructions_file missing: {ifile}")

    # Always-required files under prompts_dir
    static_files = [
        "alert_storm.md",
        "graph_explorer/core_schema.md",
        "graph_explorer/core_instructions.md",
        "graph_explorer/description.md",
        "graph_explorer/language_gremlin.md",
        "graph_explorer/language_mock.md",
    ]

    for rel_path in static_files:
        p = prompts_dir / rel_path
        if not p.exists():
            errors.append(f"Required prompt file missing: {rel_path}")

    # Check X-Graph rule in critical files.
    # Prompts should contain either the literal graph name OR the {graph_name}
    # placeholder (which the config router substitutes at runtime).
    # Check orchestrator + any agent with graph tool + graph_explorer core_instructions
    x_graph_files: list[tuple[str, Path]] = [
        ("graph_explorer/core_instructions.md", prompts_dir / "graph_explorer" / "core_instructions.md"),
    ]
    for agent in scenario_data.get("agents", []):
        tools = agent.get("tools", [])
        has_graph = any(t.get("spec_template") == "graph" or t.get("spec_template") == "telemetry" for t in tools)
        is_orch = agent.get("is_orchestrator", False) or agent.get("role") == "orchestrator"
        if (has_graph or is_orch) and agent.get("instructions_file"):
            ifile = agent["instructions_file"]
            x_graph_files.append((ifile, data_dir / ifile))
    for display_name, fpath in x_graph_files:
        if fpath.exists() and fpath.is_file():
            content = fpath.read_text()
            has_literal = graph_name in content
            has_placeholder = "{graph_name}" in content
            if not has_literal and not has_placeholder:
                errors.append(
                    f"X-Graph rule: {display_name} contains neither "
                    f"'{graph_name}' nor '{{graph_name}}' placeholder"
                )

    return errors


def validate_runbooks(
    scenario_dir: Path,
    scenario_data: dict,
) -> list[str]:
    """Validate runbook files exist."""
    errors: list[str] = []

    runbooks_dir = scenario_dir / scenario_data.get("paths", {}).get("runbooks", "data/knowledge/runbooks")
    if not runbooks_dir.is_dir():
        warn("No runbooks directory found — skipping runbook validation")
        return errors

    md_files = list(runbooks_dir.glob("*.md"))
    if not md_files:
        errors.append("No runbook .md files found in runbooks directory")
    elif len(md_files) < 4:
        warn(f"Only {len(md_files)} runbooks found (guideline: 4–6)")

    return errors


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> int:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <scenario-name>")
        print(f"Example: {sys.argv[0]} telco-noc")
        sys.exit(2)

    scenario_name = sys.argv[1]
    script_dir = Path(__file__).resolve().parent
    scenario_dir = script_dir / "scenarios" / scenario_name

    if not scenario_dir.is_dir():
        print(f"{RED}ERROR:{NC} Scenario directory not found: {scenario_dir}")
        sys.exit(2)

    print(f"\n{BOLD}Validating scenario: {scenario_name}{NC}\n")

    total_errors: list[str] = []

    # 1. scenario.yaml
    print(f"{BOLD}[1/7] scenario.yaml{NC}")
    scenario_data, errs = validate_scenario_yaml(scenario_dir)
    if errs:
        for e in errs:
            fail(e)
        total_errors.extend(errs)
    else:
        ok("scenario.yaml structure valid")

    # 2. Collect entity IDs
    print(f"\n{BOLD}[2/7] Entity CSVs{NC}")
    entities_dir = scenario_dir / scenario_data.get("paths", {}).get("entities", "data/entities")
    entity_ids = collect_entity_ids(entities_dir)
    all_ids = all_vertex_ids(entity_ids)

    if not entity_ids:
        fail("No Dim*.csv files found")
        total_errors.append("No Dim*.csv files found")
    else:
        total_entities = sum(len(v) for v in entity_ids.values())
        ok(f"{len(entity_ids)} entity files, {total_entities} total vertices")
        for fname, ids in sorted(entity_ids.items()):
            ok(f"  {fname}: {len(ids)} entities")

    # 3. graph_schema.yaml
    print(f"\n{BOLD}[3/7] graph_schema.yaml{NC}")
    errs = validate_graph_schema(scenario_dir, entity_ids)
    if errs:
        for e in errs:
            fail(e)
        total_errors.extend(errs)
    else:
        ok("graph_schema.yaml valid — all vertices & edges reference existing CSVs/columns")

    # Get vertex labels for telemetry validation
    schema_path = scenario_dir / "graph_schema.yaml"
    vertex_labels: set[str] = set()
    if schema_path.exists():
        with open(schema_path) as f:
            schema = yaml.safe_load(f)
        vertex_labels = {v.get("label", "") for v in schema.get("vertices", [])}

    # 4. Junction tables
    print(f"\n{BOLD}[4/7] Junction tables (Fact*.csv){NC}")
    errs = validate_junction_tables(entities_dir, all_ids)
    if errs:
        for e in errs:
            fail(e)
        total_errors.extend(errs)
    else:
        fact_count = len(list(entities_dir.glob("Fact*.csv"))) if entities_dir.is_dir() else 0
        ok(f"{fact_count} junction table(s) — all IDs cross-reference correctly")

    # 5. Telemetry
    print(f"\n{BOLD}[5/7] Telemetry{NC}")
    errs = validate_telemetry(scenario_dir, scenario_data, all_ids, vertex_labels)
    if errs:
        for e in errs:
            fail(e)
        total_errors.extend(errs)
    else:
        ok("Telemetry CSVs valid — all IDs, types, and no-null rule pass")

    # 6. Tickets
    print(f"\n{BOLD}[6/7] Tickets{NC}")
    errs = validate_tickets(scenario_dir, scenario_data, all_ids)
    if errs:
        for e in errs:
            fail(e)
        total_errors.extend(errs)
    else:
        ok("Ticket files valid — all entity ID references exist")

    # 7. Prompts
    print(f"\n{BOLD}[7/7] Prompts{NC}")
    errs = validate_prompts(scenario_dir, scenario_data)
    validate_runbooks(scenario_dir, scenario_data)
    if errs:
        for e in errs:
            fail(e)
        total_errors.extend(errs)
    else:
        ok("Prompt fragments valid — all files present, X-Graph rule verified")

    # Summary
    print(f"\n{'─' * 60}")
    if total_errors:
        print(f"\n{RED}{BOLD}FAILED{NC} — {len(total_errors)} error(s) found:\n")
        for i, e in enumerate(total_errors, 1):
            print(f"  {i}. {e}")
        print()
        return 1
    else:
        print(f"\n{GREEN}{BOLD}PASSED{NC} — all cross-reference checks passed ✓\n")
        return 0


if __name__ == "__main__":
    sys.exit(main())
