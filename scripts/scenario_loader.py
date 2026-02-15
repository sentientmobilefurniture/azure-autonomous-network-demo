"""
ScenarioLoader — resolves all paths and config for a named scenario.

Usage:
    from scripts.scenario_loader import ScenarioLoader

    scenario = ScenarioLoader("telco-noc")
    scenario.entities_dir        # -> Path to entity CSVs
    scenario.graph_schema        # -> Path to graph_schema.yaml
    scenario.default_alert       # -> str contents of default_alert.md
    scenario.cosmos_config       # -> dict from scenario.yaml cosmos section
    scenario.graph_styles        # -> dict of node_types -> {color, size, icon}

    ScenarioLoader.list_scenarios()  # -> [{"name": ..., "display_name": ...}, ...]
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

# Default scenarios root: <project>/data/scenarios/
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCENARIOS_DIR = _PROJECT_ROOT / "data" / "scenarios"


class ScenarioLoader:
    """Resolves all paths and config for a named scenario."""

    def __init__(self, scenario_name: str, scenarios_root: Path | None = None):
        self.name = scenario_name
        self.root = (scenarios_root or SCENARIOS_DIR) / scenario_name
        manifest_path = self.root / "scenario.yaml"
        if not manifest_path.exists():
            raise FileNotFoundError(
                f"Scenario manifest not found: {manifest_path}"
            )
        self.manifest: dict[str, Any] = yaml.safe_load(
            manifest_path.read_text()
        )

    # ── Path accessors ────────────────────────────────────────────────

    def _resolve(self, key: str) -> Path:
        """Resolve a path from the manifest's 'paths' section relative to scenario root."""
        return self.root / self.manifest["paths"][key]

    @property
    def entities_dir(self) -> Path:
        return self._resolve("entities")

    @property
    def graph_schema(self) -> Path:
        return self._resolve("graph_schema")

    @property
    def telemetry_dir(self) -> Path:
        return self._resolve("telemetry")

    @property
    def runbooks_dir(self) -> Path:
        return self._resolve("runbooks")

    @property
    def tickets_dir(self) -> Path:
        return self._resolve("tickets")

    @property
    def prompts_dir(self) -> Path:
        return self._resolve("prompts")

    @property
    def default_alert(self) -> str:
        """Return the contents of the default alert file (not the path)."""
        alert_path = self._resolve("default_alert")
        if alert_path.exists():
            return alert_path.read_text().strip()
        return ""

    # ── Config accessors ──────────────────────────────────────────────

    @property
    def display_name(self) -> str:
        return self.manifest.get("display_name", self.name)

    @property
    def domain(self) -> str:
        return self.manifest.get("domain", "unknown")

    @property
    def description(self) -> str:
        return self.manifest.get("description", "")

    @property
    def cosmos_config(self) -> dict[str, Any]:
        return self.manifest.get("cosmos", {})

    @property
    def search_indexes(self) -> list[dict[str, Any]]:
        return self.manifest.get("search_indexes", [])

    @property
    def graph_styles(self) -> dict[str, Any]:
        return self.manifest.get("graph_styles", {})

    @property
    def telemetry_baselines(self) -> dict[str, Any]:
        return self.manifest.get("telemetry_baselines", {})

    # ── Derived names (scenario-prefixed) ─────────────────────────────

    def gremlin_graph_name(self) -> str:
        """Scenario-prefixed Gremlin graph name, e.g. 'telco-noc-topology'."""
        base = self.cosmos_config.get("gremlin", {}).get("graph", "topology")
        return f"{self.name}-{base}"

    def gremlin_database_name(self) -> str:
        """Shared Gremlin database name (not prefixed)."""
        return self.cosmos_config.get("gremlin", {}).get(
            "database", "networkgraph"
        )

    def telemetry_database_name(self) -> str:
        """Scenario-prefixed NoSQL telemetry database name."""
        base = self.cosmos_config.get("nosql", {}).get("database", "telemetry")
        return f"{self.name}-{base}"

    def telemetry_containers(self) -> list[dict[str, Any]]:
        """Container definitions from the manifest."""
        return self.cosmos_config.get("nosql", {}).get("containers", [])

    def telemetry_container_names(self) -> set[str]:
        """Set of valid container names for this scenario."""
        return {c["name"] for c in self.telemetry_containers()}

    # ── Serialisation (for /api/scenario endpoint) ────────────────────

    def to_api_response(self) -> dict[str, Any]:
        """Return a dict suitable for the /api/scenario REST response."""
        return {
            "name": self.name,
            "display_name": self.display_name,
            "domain": self.domain,
            "description": self.description,
            "default_alert": self.default_alert,
            "graph_styles": self.graph_styles,
            "telemetry_baselines": self.telemetry_baselines,
            "cosmos": {
                "gremlin_graph": self.gremlin_graph_name(),
                "gremlin_database": self.gremlin_database_name(),
                "telemetry_database": self.telemetry_database_name(),
                "telemetry_containers": list(self.telemetry_container_names()),
            },
        }

    # ── Class methods ─────────────────────────────────────────────────

    @classmethod
    def list_scenarios(
        cls, scenarios_root: Path | None = None
    ) -> list[dict[str, Any]]:
        """List all available scenarios with basic metadata.

        Returns a list of dicts with 'name', 'display_name', and 'domain'.
        """
        root = scenarios_root or SCENARIOS_DIR
        scenarios: list[dict[str, Any]] = []
        if not root.exists():
            return scenarios
        for child in sorted(root.iterdir()):
            manifest = child / "scenario.yaml"
            if child.is_dir() and manifest.exists():
                try:
                    loader = cls(child.name, scenarios_root=root)
                    scenarios.append(
                        {
                            "name": loader.name,
                            "display_name": loader.display_name,
                            "domain": loader.domain,
                        }
                    )
                except Exception:
                    pass  # skip broken scenarios
        return scenarios

    @classmethod
    def get_default_scenario(cls) -> str:
        """Read DEFAULT_SCENARIO from env, defaulting to 'telco-noc'."""
        return os.getenv("DEFAULT_SCENARIO", "telco-noc")

    def __repr__(self) -> str:
        return f"ScenarioLoader('{self.name}')"
