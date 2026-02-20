import React, { createContext, useContext, useEffect, useState } from 'react';
import { ScenarioConfig, SCENARIO_DEFAULTS, getScenario } from './config';

const ScenarioCtx = createContext<ScenarioConfig>(SCENARIO_DEFAULTS);
export const useScenario = () => useContext(ScenarioCtx);

export const ScenarioProvider: React.FC<{children: React.ReactNode}> = ({children}) => {
  const [scenario, setScenario] = useState<ScenarioConfig>(SCENARIO_DEFAULTS);
  useEffect(() => {
    getScenario()
      .then(setScenario)
      .catch((err) => console.error('[ScenarioContext] Failed to fetch scenario:', err));
  }, []);
  return <ScenarioCtx.Provider value={scenario}>{children}</ScenarioCtx.Provider>;
};
