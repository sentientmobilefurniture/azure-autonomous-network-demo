"""
Config Validator — validate scenario configuration before provisioning.

Ensures that scenario.yaml agent definitions are well-formed before
they are passed to AgentProvisioner.provision_from_config().

Usage:
    from config_validator import validate_scenario_config, ConfigValidationError

    try:
        validate_scenario_config(config)
    except ConfigValidationError as e:
        print(e.errors)
"""

from __future__ import annotations


class ConfigValidationError(Exception):
    """Raised when scenario config fails validation."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__(f"Config validation failed: {'; '.join(errors)}")


_REQUIRED_AGENT_FIELDS = {"name", "model"}
_VALID_TOOL_TYPES = {"openapi", "azure_ai_search"}


def validate_scenario_config(config: dict) -> None:
    """Validate the agents section of a scenario config.

    Checks:
    - 'agents' key exists and is a non-empty list
    - Each agent has required fields (name, model)
    - Agent names are unique
    - Orchestrator connected_agents reference existing agent names
    - Tool type values are recognised
    - At most one orchestrator is defined

    Raises:
        ConfigValidationError: If any validation checks fail.
    """
    errors: list[str] = []

    agents = config.get("agents")
    if not agents:
        raise ConfigValidationError(["Config missing 'agents' list or it is empty"])

    if not isinstance(agents, list):
        raise ConfigValidationError(["'agents' must be a list"])

    seen_names: set[str] = set()
    orchestrator_count = 0

    for i, agent_def in enumerate(agents):
        label = agent_def.get("name", f"agents[{i}]")

        # Required fields
        for field in _REQUIRED_AGENT_FIELDS:
            if not agent_def.get(field):
                errors.append(f"{label}: missing required field '{field}'")

        # Unique names
        name = agent_def.get("name")
        if name:
            if name in seen_names:
                errors.append(f"Duplicate agent name: '{name}'")
            seen_names.add(name)

        # Orchestrator count
        if agent_def.get("is_orchestrator"):
            orchestrator_count += 1

        # Tool validation
        for j, tool_def in enumerate(agent_def.get("tools", [])):
            tool_type = tool_def.get("type")
            if tool_type not in _VALID_TOOL_TYPES:
                errors.append(
                    f"{label}.tools[{j}]: unknown tool type '{tool_type}' "
                    f"(expected one of {_VALID_TOOL_TYPES})"
                )
            if tool_type == "azure_ai_search" and not tool_def.get("index_key"):
                errors.append(f"{label}.tools[{j}]: 'azure_ai_search' tool requires 'index_key'")
            if tool_type == "openapi" and not tool_def.get("spec_template"):
                errors.append(f"{label}.tools[{j}]: 'openapi' tool requires 'spec_template'")

    # Orchestrator checks
    if orchestrator_count > 1:
        errors.append(f"Multiple orchestrators defined ({orchestrator_count}); expected at most 1")

    # Connected agent references
    for agent_def in agents:
        if agent_def.get("is_orchestrator"):
            for ref in agent_def.get("connected_agents", []):
                if ref not in seen_names:
                    errors.append(
                        f"{agent_def['name']}: connected_agents references "
                        f"unknown agent '{ref}'"
                    )

    if errors:
        raise ConfigValidationError(errors)
