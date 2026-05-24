import React from 'react';

interface LogItem {
  time: string;
  message: string;
}

interface Props {
  recentActions: LogItem[];
}

export default function AuditLog({ recentActions }: Props) {
  return (
    <div className="space-y-6">
      <div className="bg-surface border border-border rounded p-4">
        <div className="text-xs font-bold uppercase text-primary mb-3">Live Connectivity Audit Log</div>
        <div className="bg-background border border-border rounded p-3 font-mono text-[11px] text-muted h-64 overflow-y-auto space-y-2">
          {recentActions?.map((log, i) => (
            <div key={i} className="border-b border-border/50 pb-1.5 last:border-0">
              <span className="text-accent-blue font-bold">[{log.time}]</span>{' '}
              <span className="text-primary">{log.message}</span>
            </div>
          ))}
          {(!recentActions || recentActions.length === 0) && (
            <div className="text-center py-4 text-xs text-muted">Listening for live execution telemetries...</div>
          )}
        </div>
      </div>
    </div>
  );
}
