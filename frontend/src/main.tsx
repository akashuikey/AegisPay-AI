import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { AuthGate } from "./components/AuthGate";
import { ErrorBoundary } from "./components/error-boundary";
import "./index.css";

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error("Failed to find the root element");
}

ReactDOM.createRoot(rootElement).render(
  <React.StrictMode>
    <ErrorBoundary>
      <AuthGate>
        {(operator, onLogout) => (
          <>
            <App />
            <button
              type="button"
              onClick={onLogout}
              title={`Signed in as ${operator.username}`}
              style={{
                position: "fixed",
                top: 10,
                right: 12,
                zIndex: 1000,
                padding: "6px 12px",
                borderRadius: 8,
                border: "1px solid #2c3b4e",
                background: "#131c28",
                color: "#c3d0de",
                fontSize: 12,
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              {operator.username} · Sign out
            </button>
          </>
        )}
      </AuthGate>
    </ErrorBoundary>
  </React.StrictMode>
);
