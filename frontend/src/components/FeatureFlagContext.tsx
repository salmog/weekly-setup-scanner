import React, { createContext, useContext, useState, useEffect } from 'react';

interface FeatureFlags {
  useV2Workbench: boolean;
  useV2AnalyticsTab: boolean;
  canaryRollbackOverride: boolean;
}

const FeatureFlagContext = createContext<{ flags: FeatureFlags; refreshFlags: () => Promise<void> } | undefined>(undefined);

export function FeatureFlagProvider({ children }: { children: React.ReactNode }) {
  const [flags, setFlags] = useState<FeatureFlags>({
    useV2Workbench: true, // Dev default enabled
    useV2AnalyticsTab: true,
    canaryRollbackOverride: false
  });

  const refreshFlags = async () => {
    try {
      // Points directly to our active Python API layer
      const res = await fetch('http://172.237.145.214:8080/api/v2/flags');
      const networkFlags = await res.json();
      setFlags(networkFlags);
    } catch {
      // If backend flag service isn't built yet, fail-safe to keeping V2 active for local dev
      setFlags({ useV2Workbench: true, useV2AnalyticsTab: true, canaryRollbackOverride: false });
    }
  };

  useEffect(() => { refreshFlags(); }, []);

  return (
    <FeatureFlagContext.Provider value={{ flags, refreshFlags }}>
      {children}
    </FeatureFlagContext.Provider>
  );
}

export const useFeatureFlags = () => {
  const context = useContext(FeatureFlagContext);
  if (!context) throw new Error("FeatureFlagContext error.");
  return context;
};
