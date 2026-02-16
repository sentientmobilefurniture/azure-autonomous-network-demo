import { ModalShell } from './ModalShell';
import { FabricSetupTab } from './settings/FabricSetupTab';
import { useFabricDiscovery } from '../hooks/useFabricDiscovery';
import { useScenarioContext } from '../context/ScenarioContext';

interface Props {
  open: boolean;
  onClose: () => void;
}

/**
 * Standalone Fabric Setup modal — shown next to the scenario chip
 * when the active scenario uses the fabric-gql backend.
 */
export function FabricSetupModal({ open, onClose }: Props) {
  const { activeScenario } = useScenarioContext();
  const fabric = useFabricDiscovery();

  if (!open) return null;

  return (
    <ModalShell title="Fabric Setup" onClose={onClose}>
      <FabricSetupTab activeScenario={activeScenario} fabric={fabric} />
    </ModalShell>
  );
}
