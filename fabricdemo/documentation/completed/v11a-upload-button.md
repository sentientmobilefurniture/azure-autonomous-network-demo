# Feature: Direct Upload + Kill Settings Modal

## What Changed

### Settings modal → deleted
The ⚙ Settings modal was a 4-tab monolith (Scenarios, Data Sources, Upload, Fabric Setup) where every function had been superseded:
- **Scenario selection** → ScenarioChip dropdown (already existed)
- **Data upload** → AddScenarioModal (already existed)
- **Provisioning** → auto-triggers on scenario select
- **Custom mode** (manual data-source wiring) → power-user debug feature, removed

### Empty state → now has a primary "Upload Scenario" button
The first-run screen now opens AddScenarioModal directly with one click instead of directing users to find ⚙ → navigate tabs.

### Fabric Setup → standalone modal
Moved to its own `FabricSetupModal` with a "⬡ Fabric" button in the header bar, visible only when the active scenario uses the `fabric-gql` backend.

## Files Changed

| File | Change |
|------|--------|
| `EmptyState.tsx` | Added `onUpload` prop, replaced passive text with primary CTA button |
| `App.tsx` | Added `AddScenarioModal` state, wired `onUpload` handler |
| `Header.tsx` | Removed ⚙ button + `SettingsModal`. Added conditional "⬡ Fabric" button next to ScenarioChip |
| `FabricSetupModal.tsx` | **New** — wraps `FabricSetupTab` in `ModalShell` |

## Files Deleted

| File | Reason |
|------|--------|
| `SettingsModal.tsx` | Superseded — all functions available elsewhere |
| `settings/ScenarioSettingsTab.tsx` | Only consumer deleted |
| `settings/DataSourceSettingsTab.tsx` | Only consumer deleted |
| `settings/UploadSettingsTab.tsx` | Only consumer deleted |
| `BindingCard.tsx` | Only consumer (DataSourceSettingsTab) deleted |

**Kept:** `settings/FabricSetupTab.tsx` — still used by `FabricSetupModal`

## User Flow (After)

### First run (no scenarios)
```
Empty state → click "📂 Upload Scenario" → AddScenarioModal opens
    → drag & drop tarball → auto-upload all 5 data types
    → scenario saved → auto-selected → agents provisioned
    → ready to investigate
```

### Returning user (has scenarios)
```
ScenarioChip dropdown → click scenario name → auto-provision
    or → click "+ New Scenario" → AddScenarioModal
```

### Fabric scenario
```
Header shows "⬡ Fabric" button → click → FabricSetupModal
    → discovery, ontology selection, provision pipeline
```
