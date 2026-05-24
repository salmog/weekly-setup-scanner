import React from 'react';

interface Props {
  commandQuery: string;
  setCommandQuery: (val: string) => void;
  handleForceScan: () => Promise<void>;
  scanning: boolean;
  marketStatus: string;
  fetchLiveState: () => Promise<void>;
}

export default function Header({ commandQuery, setCommandQuery, handleForceScan, scanning, marketStatus, fetchLiveState }: Props) {
  
  // Terminal execution processor
  const handleKeyDown = async (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && commandQuery.startsWith('/')) {
      const currentCmd = commandQuery;
      setCommandQuery(''); // Wipe terminal input array immediately for clean UX
      
      try {
        await fetch('http://172.237.145.214:8080/api/v2/command', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ raw_command: currentCmd })
        });
        await fetchLiveState(); // Pull updated core state immediately
      } catch (err) {
        console.error("Failed to forward instruction parameter array:", err);
      }
    }
  };

  return (
    <header className="h-14 bg-surface border-b border-border px-6 flex items-center justify-between shrink-0">
      <div className="flex items-center space-x-4 w-1/3">
        <span className="text-muted text-xs">⌘K</span>
        <input 
          type="text" 
          placeholder="Type execution command (e.g., /pause S1) + Enter..." 
          value={commandQuery} 
          onChange={(e) => setCommandQuery(e.target.value)} 
          onKeyDown={handleKeyDown}
          className="bg-background/50 border border-border rounded px-3 py-1.5 text-xs text-primary placeholder-muted focus:outline-none focus:border-primary w-full transition" 
        />
      </div>
      <div className="flex items-center space-x-6 text-xs font-medium">
        <button 
          onClick={handleForceScan}
          disabled={scanning}
          className="bg-background border border-border text-[10px] font-black uppercase tracking-wider px-3 py-1.5 rounded hover:border-success/40 transition disabled:opacity-40 text-primary cursor-pointer"
        >
          {scanning ? '📡 EXECUTING SCAN SEQUENCE...' : '⚡ FORCE CORE PIPELINE SCAN'}
        </button>
        <div className="flex items-center space-x-2">
          <span className="text-muted">Exchange:</span>
          <span className={marketStatus?.includes("OPEN") ? "text-success font-bold" : "text-warning font-bold"}>
            {marketStatus || "CLOSED"}
          </span>
        </div>
        <div className="flex items-center space-x-2">
          <span className="text-muted">Data Engine:</span>
          <span className="text-success font-bold">PYTHON API LIVE</span>
        </div>
      </div>
    </header>
  );
}
