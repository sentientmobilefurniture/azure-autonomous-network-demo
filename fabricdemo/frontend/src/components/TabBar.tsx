interface TabBarProps {
  activeTab: 'investigate' | 'resources';
  onTabChange: (tab: 'investigate' | 'resources') => void;
}

export function TabBar({ activeTab, onTabChange }: TabBarProps) {
  const tabs = [
    { id: 'investigate' as const, label: '▸ Investigate' },
    { id: 'resources' as const, label: '◇ Resources' },
  ];

  return (
    <div role="tablist" aria-label="Main navigation" className="flex border-b border-white/10 bg-neutral-bg2 px-4 shrink-0">
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
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
