interface TabBarProps {
  activeTab: 'investigate' | 'info' | 'resources';
  onTabChange: (tab: 'investigate' | 'info' | 'resources') => void;
}

export function TabBar({ activeTab, onTabChange }: TabBarProps) {
  return (
    <div className="flex border-b border-white/10 bg-neutral-bg2 px-4 shrink-0">
      <button
        className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
          activeTab === 'investigate'
            ? 'border-brand text-brand'
            : 'border-transparent text-text-secondary hover:text-text-primary'
        }`}
        onClick={() => onTabChange('investigate')}
      >
        ▸ Investigate
      </button>
      <button
        className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
          activeTab === 'info'
            ? 'border-brand text-brand'
            : 'border-transparent text-text-secondary hover:text-text-primary'
        }`}
        onClick={() => onTabChange('info')}
      >
        ℹ Scenario Info
      </button>
      <button
        className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
          activeTab === 'resources'
            ? 'border-brand text-brand'
            : 'border-transparent text-text-secondary hover:text-text-primary'
        }`}
        onClick={() => onTabChange('resources')}
      >
        ◇ Resources
      </button>
    </div>
  );
}
