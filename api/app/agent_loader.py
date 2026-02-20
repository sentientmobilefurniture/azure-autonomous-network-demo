"""Load the declarative agent from YAML at startup."""

import logging
import os
from pathlib import Path

from azure.identity import DefaultAzureCredential
from agent_framework_declarative import AgentFactory

from app.tools import TOOL_BINDINGS

logger = logging.getLogger(__name__)

_agent = None
_credential = None
AGENTS_DIR = Path(__file__).parent.parent / "agents"


def _get_credential():
    """Return a cached DefaultAzureCredential."""
    global _credential
    if _credential is None:
        _credential = DefaultAzureCredential()
    return _credential


def load_agent():
    """Create the agent from the declarative YAML definition.

    Called once during FastAPI lifespan startup.
    """
    global _agent

    # Ensure env vars are mapped for the framework
    os.environ.setdefault(
        "AZURE_AI_PROJECT_ENDPOINT",
        os.environ.get("PROJECT_ENDPOINT", ""),
    )
    os.environ.setdefault(
        "AZURE_AI_MODEL_DEPLOYMENT_NAME",
        os.environ.get("MODEL_DEPLOYMENT_NAME", "gpt-4.1"),
    )

    yaml_path = AGENTS_DIR / "orchestrator.yaml"
    logger.info("Loading declarative agent from %s", yaml_path)

    factory = AgentFactory(
        bindings=TOOL_BINDINGS,
        safe_mode=False,  # Allow =Env. expressions in YAML
        client_kwargs={"credential": _get_credential()},
    )
    _agent = factory.create_agent_from_yaml_path(str(yaml_path))
    logger.info("Agent loaded: %s", getattr(_agent, "name", "unknown"))
    return _agent


def get_agent():
    """Return the loaded agent singleton."""
    if _agent is None:
        raise RuntimeError("Agent not loaded. Call load_agent() at startup.")
    return _agent
