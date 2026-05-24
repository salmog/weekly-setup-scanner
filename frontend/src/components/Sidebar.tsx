import React from 'react';

interface Props {
  activeTab: string;
  setActiveTab: (tab: string) => void;
}

export default function Sidebar({ activeTab, setActiveTab }: Props) {
  return (
    <aside className="w-64 bg-surface border-r border-border flex flex-col justify-between shrink-0">
      <div>
        <div className="p-6 border-b border-border flex items-center space-x-3">
          <div className="w-3 h-3 rounded-full bg-success animate-pulse" />
          <span className="font-extrabold tracking-tight text-sm text-primary">MIT-LOOP PRO ENGINE</span>
        </div>
        <nav className="p-4 space-y-1">
          <button onClick={() => setActiveTab('workspace')} className={`w-full text-left px-4 py-2.5 rounded text-xs font-bold transition flex items-center space-x-2 ${activeTab === 'workspace' ? 'bg-border text-primary' : 'text-muted hover:text-primary hover:bg-border/30'}`}>
            <span>📊 Quantitative Workspace</span>
          </button>
          <button onClick={() => setActiveTab('analytics')} className={`w-full text-left px-4 py-2.5 rounded text-xs font-bold transition flex items-center space-x-2 ${activeTab === 'analytics' ? 'bg-border text-primary' : 'text-muted hover:text-primary hover:bg-border/30'}`}>
            <span>📈 Institutional Analytics</span>
          </button>
          <button onClick={() => setActiveTab('connectivity')} className={`w-full text-left px-4 py-2.5 rounded text-xs font-bold transition flex items-center space-x-2 ${activeTab === 'connectivity' ? 'bg-border text-primary' : 'text-muted hover:text-primary hover:bg-border/30'}`}>
            <span>🔌 Broker Connectivity</span>
          </button>
        </nav>
      </div>
      <div className="p-4 border-t border-border text-[11px] text-muted space-y-1 bg-background/20">
        <div>Client Architecture: v2.6.0-Modular</div>
        <div>Environment: API Connected Sandbox</div>
      </div>
    </aside>
  );
}
