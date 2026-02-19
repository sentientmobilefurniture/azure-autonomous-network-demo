/**
 * Central tooltip / help-text definitions for UI controls.
 *
 * Keep all user-facing explanatory text here so it can be reviewed,
 * translated, or updated in one place rather than scattered across
 * individual components.
 */

/* ------------------------------------------------------------------ */
/*  Health-check buttons  (HealthButtonBar)                            */
/* ------------------------------------------------------------------ */

export const HEALTH_BUTTON_TOOLTIPS: Record<string, string> = {
  'fabric-sources':
    'Ping each Fabric data source (Graph via GQL, Telemetry via KQL, AI Search indexes) ' +
    'and report whether they are reachable. Use this after resuming a paused Fabric capacity ' +
    'to confirm connectivity.',

  'fabric-discovery':
    'Invalidate the cached Fabric workspace configuration and re-discover items ' +
    '(Graph Model, Eventhouse, KQL Database) from the Fabric REST API. ' +
    'Useful after provisioning new Fabric resources or changing workspace items.',

  'agent-health':
    'Check the health of all backend services — AI Foundry connection, ' +
    'Fabric GQL & KQL backends, and AI Search. Returns a per-service status summary.',

  'agent-discovery':
    'Invalidate the cached agent list and re-query AI Foundry for provisioned agents. ' +
    'Use this after running the agent provisioner or if agents appear missing.',
};

/* ------------------------------------------------------------------ */
/*  Header toggle buttons                                              */
/* ------------------------------------------------------------------ */

export const HEADER_TOOLTIPS: Record<string, string> = {
  'agents-show': 'Show the agent bar — displays all provisioned AI agents and their status.',
  'agents-hide': 'Hide the agent bar to reclaim vertical space.',
  'health-show': 'Show the health-check bar with manual connectivity buttons.',
  'health-hide': 'Hide the health-check bar to reclaim vertical space.',
  'services':    'Open the detailed service health popover.',
  'dark-mode':   'Switch to dark mode.',
  'light-mode':  'Switch to light mode.',
};
