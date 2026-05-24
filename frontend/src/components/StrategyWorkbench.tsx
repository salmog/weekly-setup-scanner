import React, { useState, useEffect } from 'react';

interface Props {
  strategy: any;
  onClose: () => void;
}

export default function StrategyWorkbench({ strategy, onClose }: Props) {
  const [activeTab, setActiveTab] = useState('overview');
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  // Operational Mutation: Forward target validation state up network pipe
  const handleLifecyclePromote = async (targetStatus: string) => {
    try {
      await fetch('http://172.237.145.214:8080/api/v2/strategy/promote', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ strategy_key: strategy.strategy_key_raw, next_status: targetStatus })
      });
    } catch (err) {
      console.error("Lifecycle configuration update failure:", err);
    }
  };

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const tabs = [
    { id: 'overview', name: 'Overview' },
    { id: 'live', name: 'Live Metrics' },
    { id: 'backtest', name: 'Backtest Metrics' },
    { id: 'python', name: 'Python Logic' },
    { id: 'pine', name: 'Pine Validation' },
    { id: 'risk', name: 'Risk Rules' },
    { id: 'entry', name: 'Entry Rules' },
    { id: 'exit', name: 'Exit Rules' },
    { id: 'logs', name: 'Execution Logs' },
    { id: 'ai', name: 'AI Commentary' },
  ];

  return (
    <div className="fixed inset-0 z-50 bg-background/90 backdrop-blur-sm flex flex-col w-screen h-screen text-primary">
      <header className="h-14 bg-surface border-b border-border px-6 flex items-center justify-between shrink-0">
        <div className="flex items-center space-x-3">
          <span className="text-[10px] bg-background text-success px-2 py-0.5 rounded font-mono border border-success/30 font-bold">
            {strategy.strategy_id}
          </span>
          <h2 className="text-sm font-black tracking-tight">{strategy.strategy_name} // WORKBENCH</h2>
          <span className="text-xs text-muted">|</span>
          <span className="text-xs text-warning uppercase font-extrabold tracking-wider bg-background px-2 py-0.5 border border-border rounded">
            State: {strategy.validation_status}
          </span>
        </div>
        <button onClick={onClose} className="text-muted hover:text-primary text-xs font-bold transition px-3 py-1.5 border border-border rounded bg-background/50 cursor-pointer">
          ESC CLOSE
        </button>
      </header>

      <div className="flex flex-1 min-h-0">
        <aside className="w-56 bg-surface/40 border-r border-border p-3 flex flex-col justify-between shrink-0">
          <div className="space-y-0.5">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`w-full text-left px-3 py-2 rounded text-xs font-bold transition cursor-pointer ${
                  activeTab === tab.id ? 'bg-border text-primary' : 'text-muted hover:text-primary hover:bg-border/20'
                }`}
              >
                {tab.name}
              </button>
            ))}
          </div>

          {/* Interactive Environment Progression Control Unit */}
          <div className="border-t border-border/60 pt-3 p-1 space-y-1.5">
            <label className="text-[9px] text-muted font-black tracking-widest uppercase block">Environment Shift</label>
            <div className="grid grid-cols-2 gap-1.5">
              <button 
                onClick={() => handleLifecyclePromote('BACKTESTING')}
                className="bg-background border border-border hover:border-warning/40 text-[10px] font-bold py-1.5 rounded text-primary transition cursor-pointer"
              >
                TESTING
              </button>
              <button 
                onClick={() => handleLifecyclePromote('LIVE_APPROVED')}
                className="bg-background border border-border hover:border-success/40 text-[10px] font-bold py-1.5 rounded text-success transition cursor-pointer"
              >
                GO LIVE
              </button>
            </div>
          </div>
        </aside>

        <main className="flex-1 p-6 overflow-y-auto bg-background min-w-0">
          {activeTab === 'overview' && (
            <div className="space-y-6 max-w-4xl">
              <div className="bg-surface border border-border rounded p-5">
                <h4 className="text-xs font-bold uppercase tracking-wider text-muted mb-2">Architectural Summary</h4>
                <p className="text-xs text-primary leading-relaxed font-medium">
                  Isolated systematic configuration utilizing structural {strategy.timeframe?.join(', ')} data arrays. Real-time updates route dependencies via {strategy.signal_engine} mechanisms directly into {strategy.execution_engine}.
                </p>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="bg-surface border border-border rounded p-4">
                  <span className="text-[10px] text-muted font-bold block uppercase mb-1">Asset Classes Matrix</span>
                  <div className="text-xs font-bold text-primary">{strategy.asset_class?.join(', ')}</div>
                </div>
                <div className="bg-surface border border-border rounded p-4">
                  <span className="text-[10px] text-muted font-bold block uppercase mb-1">Risk Parameter Settings</span>
                  <div className="text-xs font-bold text-warning">{strategy.risk_model}</div>
                </div>
              </div>
            </div>
          )}

          {activeTab === 'live' && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 max-w-4xl">
              <div className="bg-surface border border-border rounded p-4">
                <div className="text-[10px] text-muted font-bold uppercase">Dynamic Allocation</div>
                <div className="text-sm font-black text-primary mt-1">${strategy.live_metrics?.currentAllocation.toLocaleString()}</div>
              </div>
              <div className="bg-surface border border-border rounded p-4">
                <div className="text-[10px] text-muted font-bold uppercase">Active Risk Positions</div>
                <div className="text-sm font-black text-primary mt-1">{strategy.live_metrics?.activePositions}</div>
              </div>
              <div className="bg-surface border border-border rounded p-4">
                <div className="text-[10px] text-muted font-bold uppercase">Pending REST Gateways</div>
                <div className="text-sm font-black text-primary mt-1">{strategy.live_metrics?.pendingOrders}</div>
              </div>
            </div>
          )}

          {activeTab === 'backtest' && (
            <div className="bg-surface border border-border rounded p-5 max-w-4xl space-y-4">
              <h3 className="text-xs font-bold uppercase text-muted">Baseline Static Evaluation Parameters</h3>
              <div className="grid grid-cols-2 gap-6 text-xs font-medium">
                <div className="flex justify-between border-b border-border/40 pb-2">
                  <span className="text-muted">Historical Samples Horizon</span>
                  <span className="text-primary font-bold">{strategy.performance_metrics?.backtestPeriod}</span>
                </div>
                <div className="flex justify-between border-b border-border/40 pb-2">
                  <span className="text-muted">Target Verification Win Rate</span>
                  <span className="text-success font-bold">{strategy.performance_metrics?.winRate?.toFixed(1)}%</span>
                </div>
              </div>
            </div>
          )}

          {(activeTab === 'python' || activeTab === 'pine') && (
            <div className="flex flex-col h-full space-y-4">
              <div className="flex justify-between items-center">
                <span className="text-xs font-bold text-muted uppercase">Side-by-Side Canvas</span>
                <button 
                  onClick={() => handleCopy(activeTab === 'python' ? strategy.python_logic_reference : strategy.pine_logic_reference)}
                  className="bg-surface border border-border text-[11px] font-bold px-3 py-1 rounded hover:bg-border transition text-primary cursor-pointer"
                >
                  {copied ? 'COPIED TO CLIPBOARD' : 'COPY COMPILER CODE'}
                </button>
              </div>
              <div className="grid grid-cols-2 gap-4 flex-1 min-h-[400px]">
                <div className="bg-surface border border-border rounded p-4 font-mono text-xs text-muted overflow-auto whitespace-pre leading-relaxed">
                  <div className="text-[10px] text-primary font-bold uppercase font-sans border-b border-border/40 pb-2 mb-2">Python Implementation</div>
                  {strategy.python_logic_reference}
                </div>
                <div className="bg-surface border border-border rounded p-4 font-mono text-xs text-muted overflow-auto whitespace-pre leading-relaxed">
                  <div className="text-[10px] text-primary font-bold uppercase font-sans border-b border-border/40 pb-2 mb-2">Pine Script</div>
                  {strategy.pine_logic_reference}
                </div>
              </div>
            </div>
          )}

          {activeTab === 'risk' && (
            <div className="bg-surface border border-border rounded p-5 max-w-4xl">
              <h3 className="text-xs font-bold uppercase text-muted mb-3">Hard-Coded Margin Controls</h3>
              <div className="text-xs font-mono text-danger bg-background/50 border border-danger/20 p-3 rounded leading-relaxed">
                {strategy.risk_rules_reference}
              </div>
            </div>
          )}

          {activeTab === 'entry' && (
            <div className="bg-surface border border-border rounded p-4 max-w-4xl text-xs font-medium">
              <div className="text-success font-mono leading-relaxed">{strategy.entry_rules_reference}</div>
            </div>
          )}

          {activeTab === 'exit' && (
            <div className="bg-surface border border-border rounded p-4 max-w-4xl text-xs font-medium">
              <div className="text-danger font-mono leading-relaxed">{strategy.exit_rules_reference}</div>
            </div>
          )}

          {activeTab === 'logs' && (
            <div className="bg-surface border border-border rounded p-4 max-w-4xl font-mono text-xs text-muted h-96 overflow-y-auto space-y-2 bg-background/20">
              {strategy.execution_logs_reference?.map((log: any, i: number) => (
                <div key={i} className="border-b border-border/30 pb-1 last:border-0">
                  <span className="text-accent-blue font-bold">[{log.time}]</span>{' '}
                  <span className="text-primary">{log.msg}</span>
                </div>
              ))}
            </div>
          )}

          {activeTab === 'ai' && (
            <div className="bg-surface border border-border rounded p-5 max-w-4xl space-y-3">
              <h3 className="text-xs font-bold uppercase text-primary">🤖 Machine Narrative</h3>
              <p className="text-xs text-muted leading-relaxed font-semibold">
                "{strategy.ai_commentary_reference}"
              </p>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
