/**
 * Central tooltip / help-text definitions for UI controls.
 *
 * Keep all user-facing explanatory text here so it can be reviewed,
 * translated, or updated in one place rather than scattered across
 * individual components.
 */

/* ------------------------------------------------------------------ */
/*  Header toggle buttons                                              */
/* ------------------------------------------------------------------ */

export const HEADER_TOOLTIPS: Record<string, string> = {
  'tabs-show':      'Show the navigation tabs (Investigate, Resources, Scenario).',
  'tabs-hide':      'Hide the navigation tabs to reclaim vertical space.',
  'services':       'Open the Services panel — view and health-check all discoverable resources.',
  'open-foundry':   'Open the Azure AI Foundry portal in a new tab.',
  'open-fabric':    'Open the Microsoft Fabric developer portal in a new tab.',
  'dark-mode':      'Switch to dark mode.',
  'light-mode':     'Switch to light mode.',
};
