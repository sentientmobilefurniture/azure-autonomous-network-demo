interface TabBarProps {
  activeTab: 'investigate' | 'resources' | 'scenario' | 'ontology';
  onTabChange: (tab: 'investigate' | 'resources' | 'scenario' | 'ontology') => void;
}

export function TabBar({ activeTab, onTabChange }: TabBarProps) {
  const tabs = [
    { id: 'investigate' as const, label: '▸ Investigate', tooltip: '' },
    { id: 'resources' as const, label: '◇ Resources', tooltip: 'Regenerate data/architecture_graph.json if architecture changes or new tools are added' },
    { id: 'scenario' as const, label: '📋 Scenario', tooltip: '' },
    { id: 'ontology' as const, label: '🔗 Graph Ontology', tooltip: 'Graph entity types, relationships, and query patterns' },
  ];

  return (
    <div role="tablist" aria-label="Main navigation" className="flex border-b border-border bg-neutral-bg2 px-4 shrink-0">
      {tabs.map(tab => (
        <button
          key={tab.id}
          role="tab"
          aria-selected={activeTab === tab.id}
          aria-controls={`tabpanel-${tab.id}`}
          className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
            activeTab === tab.id
              ? 'border-brand text-brand'
              : 'border-transparent text-text-secondary hover:text-text-primary'
          }`}
          onClick={() => onTabChange(tab.id)}
          title={tab.tooltip || undefined}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
