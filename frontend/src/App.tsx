import React, { useState, useEffect } from 'react';
import Sidebar from './components/Sidebar';
import Header from './components/Header';
import QuantitativeWorkspace from './components/QuantitativeWorkspace';
import BrokerConnectivity from './components/BrokerConnectivity';
import InstitutionalAnalytics from './components/InstitutionalAnalytics';
import { StrategyMetadata } from './types/strategy';

const STATIC_STRATEGY_DATA: Record<string, Partial<StrategyMetadata>> = {
  "S1_BodyStrict": { strategy_id: "S1", strategy_name: "Strategy 1: Body Strict", timeframe: ["1W"], asset_class: ["STOCKS", "ETF"], execution_engine: "Alpaca_OTO_Router", signal_engine: "IBKR_Local_CSV", risk_model: "Fixed_1_Percent" },
  "S2_WickScaled": { strategy_id: "S2", strategy_name: "Strategy 2: Wick Scaled", timeframe: ["1W"], asset_class: ["STOCKS", "FUTURES"], execution_engine: "Alpaca_Scaled_Router", signal_engine: "IBKR_Local_CSV", risk_model: "Scaled_2_Percent" },
  "S3_WickStrict": { strategy_id: "S3", strategy_name: "Strategy 3: Wick Strict", timeframe: ["1W", "1D"], asset_class: ["OPTIONS", "STOCKS"], execution_engine: "Alpaca_OTO_Router", signal_engine: "IBKR_Local_CSV", risk_model: "Fixed_1_Percent" }
};

export default function App() {
  const [activeTab, setActiveTab] = useState('workspace');
  const [commandQuery, setCommandQuery] = useState('');
  const [systemState, setSystemState] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [isOnline, setIsOnline] = useState(false);

  const fetchLiveStateFallback = async () => {
    try {
      const res = await fetch('http://172.237.145.214:8080/api/state');
      if (res.ok) {
        const data = await res.json();
        setSystemState(data);
        setIsOnline(true);
        setLoading(false);
      }
    } catch (err) {
      console.error("REST fallback link offline.");
      setIsOnline(false);
      setLoading(false);
    }
  };

  const handleForceScan = async () => {
    if (!isOnline) return;
    setScanning(true);
    try {
      await fetch('http://172.237.145.214:8080/api/v2/scan', { method: 'POST' });
    } catch (err) {
      console.error("Scanner signal trigger failed:", err);
    } finally {
      setScanning(false);
    }
  };

  useEffect(() => {
    let socket: WebSocket;
    
    const connectStream = () => {
      socket = new WebSocket('ws://172.237.145.214:8080/api/v2/stream');
      
      socket.onopen = () => {
        setIsOnline(true);
      };

      socket.onmessage = (event) => {
        const liveDataStream = JSON.parse(event.data);
        setSystemState(liveDataStream);
        setLoading(false);
      };

      socket.onerror = (err) => {
        console.error("WebSocket channel fault. Swapping to fallback execution checking.");
        fetchLiveStateFallback();
      };

      socket.onclose = () => {
        setIsOnline(false);
        // Attempt automatic reconnection every 4 seconds if the data pipe drops
        setTimeout(connectStream, 4000);
      };
    };

    connectStream();
    return () => socket?.close();
  }, []);

  // Defensive State Layer: Trigger connection validation layout wrapper
  if (loading) {
    return <div className="min-h-screen bg-background flex items-center justify-center text-muted font-mono text-xs">Connecting to Python Core Engine...</div>;
  }

  if (!isOnline || !systemState) {
    return (
      <div className="min-h-screen bg-background flex flex-col items-center justify-center space-y-3 font-mono text-xs text-muted">
        <div className="w-4 h-4 border-2 border-danger border-t-transparent rounded-full animate-spin" />
        <div className="text-danger font-bold uppercase tracking-wider">📡 [CORE DISCONNECTED]</div>
        <div>Awaiting Python API Gateway startup sequence on 172.237.145.214:8080...</div>
      </div>
    );
  }

  const strategies: StrategyMetadata[] = Object.entries(systemState.accounts || {}).map(([key, acc]: [string, any]) => {
    const staticData = STATIC_STRATEGY_DATA[key] || {};
    const dynamicPositions = acc?.open_positions || [];
    const bMetrics = acc?.backtest_metrics || { win_rate: 0, profit_factor: 0, max_dd: 0, sharpe: 0, trades: 0 };

    return {
      ...staticData,
      strategy_key_raw: key,
      validation_status: acc?.validation_status || "DRAFT",
      python_logic_reference: acc?.python_code || "",
      pine_logic_reference: acc?.pine_code || "",
      risk_rules_reference: acc?.risk_rules || "",
      entry_rules_reference: acc?.entry_rules || "",
      exit_rules_reference: acc?.exit_rules || "",
      ai_commentary_reference: acc?.ai_commentary || "",
      execution_logs_reference: acc?.logs || [],
      live_metrics: {
        currentAllocation: acc?.equity || 100000.00,
        availableCash: acc?.cash || 0,
        unrealizedPnL: dynamicPositions.reduce((sum: number, p: any) => sum + parseFloat(p.pnl || 0), 0),
        realizedPnLToday: acc?.day_pnl || 0,
        activePositions: dynamicPositions.length,
        pendingOrders: acc?.active_orders || 0
      },
      performance_metrics: { 
        winRate: bMetrics.win_rate, 
        profitFactor: bMetrics.profit_factor, 
        maxDrawdown: bMetrics.max_dd, 
        sharpeRatio: bMetrics.sharpe, 
        totalTrades: bMetrics.trades, 
        backtestPeriod: "2018-2026" 
      }
    } as any;
  });

  const totalAllocation = strategies.reduce((sum, s) => sum + (s.live_metrics?.currentAllocation || 0), 0);

  return (
    <div className="min-h-screen bg-background text-primary flex">
      <Sidebar activeTab={activeTab} setActiveTab={setActiveTab} />
      <main className="flex-1 flex flex-col min-w-0">
        <Header 
          commandQuery={commandQuery} 
          setCommandQuery={setCommandQuery} 
          handleForceScan={handleForceScan} 
          scanning={scanning} 
          marketStatus={systemState.market_status} 
          fetchLiveState={fetchLiveStateFallback}
        />
        {activeTab === 'workspace' && (
          <QuantitativeWorkspace 
            systemState={systemState} 
            strategies={strategies} 
            totalAllocation={totalAllocation} 
            commandQuery={commandQuery} 
            setCommandQuery={setCommandQuery} 
          />
        )}
        {activeTab === 'analytics' && <InstitutionalAnalytics strategies={strategies} systemState={systemState} />}
        {activeTab === 'connectivity' && <BrokerConnectivity />}
      </main>
    </div>
  );
}
