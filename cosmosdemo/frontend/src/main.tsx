import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import { ScenarioProvider } from './context/ScenarioContext';
import './styles/globals.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ScenarioProvider>
      <App />
    </ScenarioProvider>
  </React.StrictMode>
);
