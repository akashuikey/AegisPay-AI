import React, { useEffect, useState, useCallback } from "react";
import { CheckCircle2, XCircle, Loader2, Database, Server } from "lucide-react";
import { config } from "../config";

interface HealthData {
  status: string;
  database: string;
  timestamp: string;
  environment: string;
}

export const BackendHealthBadge: React.FC = () => {
  const [health, setHealth] = useState<HealthData | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [showDetails, setShowDetails] = useState<boolean>(false);

  const checkHealth = useCallback(async () => {
    try {
      let response: Response;
      try {
        response = await fetch(`${config.apiBaseUrl}/health/ready`);
      } catch {
        const { handleMockApiRequest } = await import("../mock/mockBackend");
        response = await handleMockApiRequest(`${config.apiBaseUrl}/health/ready`);
      }
      if (!response.ok) {
        if (response.status === 503) {
          const body: HealthData = await response.json();
          setHealth(body);
          setError("Database unavailable");
          return;
        }
        throw new Error(`HTTP ${response.status}`);
      }
      const data: HealthData = await response.json();
      setHealth(data);
      setError(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Backend unreachable");
      setHealth(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    checkHealth();
    const interval = setInterval(checkHealth, 15000);
    return () => clearInterval(interval);
  }, [checkHealth]);

  return (
    <div style={{ position: "relative" }}>
      <button
        onClick={() => setShowDetails(!showDetails)}
        className="button"
        style={{
          padding: "5px 10px",
          fontSize: "10px",
          display: "flex",
          alignItems: "center",
          gap: "6px",
          borderRadius: "8px",
          border: error ? "1px solid #fecaca" : "1px solid #bbf7d0",
          backgroundColor: error ? "#fef2f2" : "#f0fdf4",
          color: error ? "#991b1b" : "#166534",
          cursor: "pointer",
        }}
        title="Click to view backend and database connection telemetry"
        data-testid="backend-health-badge"
      >
        {loading ? (
          <>
            <Loader2 size={12} className="animate-spin" />
            <span>Checking API...</span>
          </>
        ) : error ? (
          <>
            <XCircle size={12} color="#dc2626" />
            <span>API: {error}</span>
          </>
        ) : (
          <>
            <CheckCircle2 size={12} color="#16a34a" />
            <span>API Online &bull; DB {health?.database === "connected" ? "Ready" : "Unavailable"}</span>
          </>
        )}
      </button>

      {showDetails && (
        <div
          style={{
            position: "absolute",
            top: "100%",
            right: 0,
            marginTop: "6px",
            width: "280px",
            backgroundColor: "#fff",
            border: "1px solid #dce4e9",
            borderRadius: "10px",
            boxShadow: "0 10px 25px -5px rgba(0, 0, 0, 0.15)",
            padding: "14px",
            zIndex: 50,
            fontSize: "11px",
            color: "#334155",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px", borderBottom: "1px solid #e2e8f0", paddingBottom: "6px" }}>
            <strong style={{ display: "flex", alignItems: "center", gap: "5px", color: "#0f172a" }}>
              <Server size={14} color="#2563eb" /> Backend Telemetry
            </strong>
            <button
              onClick={() => setShowDetails(false)}
              style={{ border: "none", background: "transparent", cursor: "pointer", fontSize: "14px", color: "#94a3b8" }}
            >
              &times;
            </button>
          </div>
          <div style={{ display: "grid", gap: "6px" }}>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <span style={{ color: "#64748b" }}>Target URL:</span>
              <span style={{ fontFamily: "monospace", fontSize: "10px" }}>{config.apiBaseUrl}</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <span style={{ color: "#64748b" }}>Readiness:</span>
              <span style={{ fontWeight: 600, color: health?.status === "ready" ? "#16a34a" : "#dc2626" }}>
                {health?.status || (loading ? "Checking..." : "Offline")}
              </span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <span style={{ color: "#64748b" }}>Database:</span>
              <span style={{ display: "flex", alignItems: "center", gap: "4px" }}>
                <Database size={12} />
                {health?.database || (loading ? "Checking..." : "Disconnected")}
              </span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <span style={{ color: "#64748b" }}>Environment:</span>
              <span>{health?.environment || "Unknown"}</span>
            </div>
            {health?.timestamp && (
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: "9px", color: "#94a3b8", marginTop: "4px" }}>
                <span>Last Probe:</span>
                <span>{new Date(health.timestamp).toLocaleTimeString()}</span>
              </div>
            )}
          </div>
          <button
            onClick={checkHealth}
            disabled={loading}
            className="button"
            style={{ width: "100%", marginTop: "10px", padding: "6px", fontSize: "10px" }}
          >
            Re-test Connectivity
          </button>
        </div>
      )}
    </div>
  );
};

