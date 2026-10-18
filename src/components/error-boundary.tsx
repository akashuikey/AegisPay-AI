/* eslint-disable react-refresh/only-export-components */
import {
  Component,
  type ComponentType,
  type ErrorInfo,
  type ReactNode,
} from 'react';

export interface ErrorFallbackProps {
  error: Error;
  resetError: () => void;
}

interface ErrorBoundaryProps {
  children: ReactNode;
  FallbackComponent?: ComponentType<ErrorFallbackProps>;
  /** Changing this clears a caught error. Pass the route to recover on navigation. */
  resetKey?: unknown;
}

interface ErrorBoundaryState {
  error: Error | null;
}

function toError(value: unknown): Error {
  if (value instanceof Error) {
    return value;
  }
  if (typeof value === 'string') {
    return new Error(value);
  }
  try {
    return new Error(JSON.stringify(value));
  } catch {
    return new Error(String(value));
  }
}

function DefaultFallback({ error, resetError }: ErrorFallbackProps) {
  return (
    <div style={{ minHeight: "100vh", width: "100%", display: "flex", alignItems: "center", justifyContent: "center", backgroundColor: "#f8fafc", padding: "1.5rem" }}>
      <div style={{ maxWidth: "32rem", width: "100%", textAlign: "center" }}>
        <h1 style={{ fontSize: "1.25rem", fontWeight: 600, color: "#0f172a" }}>
          Something went wrong
        </h1>
        <p style={{ marginTop: "0.5rem", fontSize: "0.875rem", color: "#475569" }}>
          This part of the application encountered an error.
        </p>
        <pre style={{ marginTop: "1rem", overflowX: "auto", borderRadius: "0.375rem", backgroundColor: "#f1f5f9", padding: "0.75rem", textAlign: "left", fontSize: "0.75rem", color: "#1e293b" }}>
          {error.message || String(error)}
        </pre>
        <button
          type="button"
          onClick={resetError}
          style={{ marginTop: "1rem", borderRadius: "0.375rem", backgroundColor: "#0f172a", padding: "0.5rem 1rem", fontSize: "0.875rem", color: "#fff", cursor: "pointer", border: "none" }}
        >
          Try again
        </button>
      </div>
    </div>
  );
}

export class ErrorBoundary extends Component<
  ErrorBoundaryProps,
  ErrorBoundaryState
> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: unknown): ErrorBoundaryState {
    return { error: toError(error) };
  }

  componentDidCatch(error: unknown, info: ErrorInfo): void {
    console.error(
      'ErrorBoundary caught an error:',
      toError(error),
      info.componentStack,
    );
  }

  componentDidUpdate(prevProps: ErrorBoundaryProps): void {
    if (
      this.state.error !== null &&
      prevProps.resetKey !== this.props.resetKey
    ) {
      this.resetError();
    }
  }

  resetError = (): void => {
    this.setState({ error: null });
  };

  render(): ReactNode {
    const { error } = this.state;
    if (error === null) {
      return this.props.children;
    }
    const Fallback = this.props.FallbackComponent ?? DefaultFallback;
    return <Fallback error={error} resetError={this.resetError} />;
  }
}
