import React, { useState, useEffect } from 'react';

interface BrokerInstance {
  broker: string;
  type: string;
  latency: string;
  status: string;
  auth: string;
}

export default function BrokerConnectivity() {
  const [brokers, setBrokers] = useState<BrokerInstance[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchBrokers = async () => {
      try {
        const res = await fetch('http://172.237.145.214:8080/api/v2/brokers');
        const data = await res.json();
        setBrokers(data.connections);
      } catch (err) {
        console.error("Broker pipeline resolution failure:", err);
      } finally {
        setLoading(false);
      }
    };
    fetchBrokers();
  }, []);

  if (loading) return <div className="p-6 text-xs text-muted font-mono">Querying data channel link headers...</div>;

  return (
    <div className="p-6 overflow-y-auto space-y-6 flex-1">
      <div className="text-xs font-bold text-muted uppercase tracking-widest mb-3">Broker Connectivity Matrix</div>
      
      <div className="grid grid-cols-1 gap-4 max-w-4xl">
        {brokers.map((b, i) => (
          <div key={i} className="bg-surface border border-border rounded p-4 flex items-center justify-between">
            <div className="flex items-center space-x-4">
              <div className={`w-2.5 h-2.5 rounded-full ${b.status === 'CONNECTED' || b.status === 'SYNCHRONIZED' ? 'bg-success animate-pulse' : 'bg-danger'}`} />
              <div>
                <h4 className="text-xs font-black text-primary tracking-tight">{b.broker}</h4>
                <p className="text-[11px] text-muted font-mono mt-0.5">{b.type} layer</p>
              </div>
            </div>

            <div className="flex items-center space-x-8 font-mono text-xs font-bold">
              <div>
                <span className="text-[10px] text-muted font-sans block uppercase font-bold mb-0.5">Network Latency</span>
                <span className="text-success">{b.latency}</span>
              </div>
              <div>
                <span className="text-[10px] text-muted font-sans block uppercase font-bold mb-0.5">Handshake Protocol</span>
                <span className="text-primary">{b.auth}</span>
              </div>
              <div className="w-28 text-end">
                <span className="text-[10px] text-muted font-sans block uppercase font-bold mb-0.5">State Line</span>
                <span className="text-success tracking-wider uppercase text-[11px]">{b.status}</span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
