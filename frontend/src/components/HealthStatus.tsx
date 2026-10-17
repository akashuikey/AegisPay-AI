import React, { useEffect, useState, useCallback } from "react";
import { CheckCircle2, XCircle, Loader2, RefreshCw, Database, Activity } from "lucide-react";
import { config } from "../config";

interface HealthData {
  status: string;
  database: string;
  timestamp: string;
  environment: string;
}

export const HealthStatus: React.FC = () => {
  const [data, setData] = useState<HealthData | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchHealth = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${config.apiBaseUrl}/health/ready`);
      if (!response.ok) {
        if (response.status === 503) {
          const errData = await response.json();
          setData(errData);
          throw new Error("Backend reachable, but Database dependency is not ready.");
        }
        throw new Error(`Health check returned unexpected HTTP status: ${response.status}`);
      }
      const json: HealthData = await response.json();
      setData(json);
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Unable to connect to backend service.");
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchHealth();
  }, [fetchHealth]);

  return (
    <div className="card" data-testid="health-status-card">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
        <h2 style={{ fontSize: "1.1rem", fontWeight: 600, display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <Activity size={20} color="var(--accent-primary)" />
          Backend Dependency Connectivity
        </h2>
        <button
          onClick={fetchHealth}
          disabled={loading}
          className="button-refresh"
          title="Re-query backend health status"
        >
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          Refresh
        </button>
      </div>

      <div style={{ margin: "1rem 0" }}>
        {loading && (
          <div className="status-badge status-loading" data-testid="status-loading">
            <Loader2 size={16} className="animate-spin" />
            Connecting to Backend...
          </div>
        )}

        {!loading && !error && data?.status === "ready" && (
          <div className="status-badge status-connected" data-testid="status-connected">
            <CheckCircle2 size={16} />
            Connected & Ready
          </div>
        )}

        {!loading && error && (
          <div className="status-badge status-error" data-testid="status-error">
            <XCircle size={16} />
            Disconnected: {error}
          </div>
        )}
      </div>

      <div className="grid">
        <div className="info-item">
          <div className="info-label">API Gateway Target</div>
          <div className="info-value" data-testid="api-target">{config.apiBaseUrl}</div>
        </div>
        <div className="info-item">
          <div className="info-label">Database Status</div>
          <div className="info-value" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
            <Database size={16} />
            <span data-testid="db-status">{data?.database || (loading ? "Checking..." : "Unavailable")}</span>
          </div>
        </div>
        <div className="info-item">
          <div className="info-label">Environment</div>
          <div className="info-value" data-testid="env-status">{data?.environment || "Unknown"}</div>
        </div>
        <div className="info-item">
          <div className="info-label">Last Probe Timestamp</div>
          <div className="info-value" style={{ fontSize: "0.8rem" }} data-testid="timestamp-status">
            {data?.timestamp ? new Date(data.timestamp).toLocaleTimeString() : "--"}
          </div>
        </div>
      </div>
    </div>
  );
};
