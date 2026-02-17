#!/usr/bin/env bash
# ============================================================================
# Generate all scenario data and create upload-ready tarballs
# ============================================================================
# Runs generate_all.sh for each scenario, then packages each one as a
# .tar.gz file ready for upload via the UI Settings page.
#
# Usage:
#   ./data/generate_all.sh              # Generate + tarball all scenarios
#   ./data/generate_all.sh telco-noc    # Generate + tarball one scenario
#
# Output (nested under scenario dir):
#   data/scenarios/telco-noc/telco-noc-graph.tar.gz
#   data/scenarios/telco-noc/telco-noc-telemetry.tar.gz
#   data/scenarios/cloud-outage/cloud-outage-graph.tar.gz
#   ...
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCENARIOS_DIR="$SCRIPT_DIR/scenarios"

GREEN='\033[0;32m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# Determine which scenarios to process
if [ $# -gt 0 ]; then
  TARGETS=("$@")
else
  TARGETS=()
  for d in "$SCENARIOS_DIR"/*/; do
    [ -f "$d/scenario.yaml" ] && TARGETS+=("$(basename "$d")")
  done
fi

echo -e "${BOLD}${CYAN}━━━ Generating scenario data + tarballs ━━━${NC}"
echo ""

for SCENARIO in "${TARGETS[@]}"; do
  SCENARIO_DIR="$SCENARIOS_DIR/$SCENARIO"

  if [ ! -d "$SCENARIO_DIR" ]; then
    echo "⚠  Scenario '$SCENARIO' not found — skipping"
    continue
  fi

  echo -e "${BOLD}▶ $SCENARIO${NC}"

  # Run data generation
  if [ -x "$SCENARIO_DIR/scripts/generate_all.sh" ]; then
    "$SCENARIO_DIR/scripts/generate_all.sh"
  else
    echo "  ⚠  No generate_all.sh found — skipping generation"
  fi

  # Create per-type tarballs (each self-contained with scenario.yaml for name resolution)
  echo "  Packaging per-type tarballs..."

  # Graph: scenario.yaml + graph_schema.yaml + data/entities/
  tar czf "$SCENARIO_DIR/$SCENARIO-graph.tar.gz" -C "$SCENARIOS_DIR" \
    "$SCENARIO/scenario.yaml" "$SCENARIO/graph_schema.yaml" "$SCENARIO/data/entities" 2>/dev/null
  echo -e "  ${GREEN}✓${NC} $SCENARIO-graph.tar.gz ($(du -h "$SCENARIO_DIR/$SCENARIO-graph.tar.gz" | cut -f1))"

  # Telemetry: scenario.yaml + data/telemetry/
  tar czf "$SCENARIO_DIR/$SCENARIO-telemetry.tar.gz" -C "$SCENARIOS_DIR" \
    "$SCENARIO/scenario.yaml" "$SCENARIO/data/telemetry" 2>/dev/null
  echo -e "  ${GREEN}✓${NC} $SCENARIO-telemetry.tar.gz ($(du -h "$SCENARIO_DIR/$SCENARIO-telemetry.tar.gz" | cut -f1))"

  # Runbooks: scenario.yaml + knowledge/runbooks/
  if [ -d "$SCENARIO_DIR/data/knowledge/runbooks" ]; then
    tar czf "$SCENARIO_DIR/$SCENARIO-runbooks.tar.gz" -C "$SCENARIOS_DIR" \
      "$SCENARIO/scenario.yaml" "$SCENARIO/data/knowledge/runbooks" 2>/dev/null
    echo -e "  ${GREEN}✓${NC} $SCENARIO-runbooks.tar.gz ($(du -h "$SCENARIO_DIR/$SCENARIO-runbooks.tar.gz" | cut -f1))"
  fi

  # Tickets: scenario.yaml + knowledge/tickets/
  if [ -d "$SCENARIO_DIR/data/knowledge/tickets" ]; then
    tar czf "$SCENARIO_DIR/$SCENARIO-tickets.tar.gz" -C "$SCENARIOS_DIR" \
      "$SCENARIO/scenario.yaml" "$SCENARIO/data/knowledge/tickets" 2>/dev/null
    echo -e "  ${GREEN}✓${NC} $SCENARIO-tickets.tar.gz ($(du -h "$SCENARIO_DIR/$SCENARIO-tickets.tar.gz" | cut -f1))"
  fi

  # Prompts: scenario.yaml + data/prompts/
  if [ -d "$SCENARIO_DIR/data/prompts" ]; then
    tar czf "$SCENARIO_DIR/$SCENARIO-prompts.tar.gz" -C "$SCENARIOS_DIR" \
      "$SCENARIO/scenario.yaml" "$SCENARIO/data/prompts" 2>/dev/null
    echo -e "  ${GREEN}✓${NC} $SCENARIO-prompts.tar.gz ($(du -h "$SCENARIO_DIR/$SCENARIO-prompts.tar.gz" | cut -f1))"
  fi

  echo ""
done

echo -e "${BOLD}${GREEN}━━━ Done ━━━${NC}"
echo ""
echo "Upload tarballs via the UI Settings page (⚙ → Upload tab):"
for SCENARIO in "${TARGETS[@]}"; do
  echo "  $SCENARIO:"
  for TYPE in graph telemetry runbooks tickets prompts; do
    T="$SCENARIOS_DIR/$SCENARIO/$SCENARIO-$TYPE.tar.gz"
    [ -f "$T" ] && echo "    $(basename "$T")"
  done
done
echo ""
