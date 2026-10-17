import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { AuthGate } from "../components/AuthGate";

describe("AuthGate", () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
    try {
      localStorage.clear();
    } catch {
      /* localStorage may be unavailable in the test env */
    }
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("shows the login form when no operator is authenticated", async () => {
    render(<AuthGate>{() => <div>CONSOLE CONTENT</div>}</AuthGate>);

    await waitFor(() =>
      expect(screen.getByLabelText(/username/i)).toBeInTheDocument()
    );
    expect(screen.queryByText("CONSOLE CONTENT")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /sign in/i })).toBeInTheDocument();
  });

  it("renders the console after a successful login", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        access_token: "signed.jwt.token",
        token_type: "bearer",
        expires_in: 3600,
        operator: { id: "op-1", username: "analyst_jordan" },
      }),
    });

    render(
      <AuthGate>
        {(operator) => <div>CONSOLE for {operator.username}</div>}
      </AuthGate>
    );

    await waitFor(() =>
      expect(screen.getByLabelText(/username/i)).toBeInTheDocument()
    );

    fireEvent.change(screen.getByLabelText(/username/i), {
      target: { value: "analyst_jordan" },
    });
    fireEvent.change(screen.getByLabelText(/password/i), {
      target: { value: "correct horse battery staple" },
    });
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() =>
      expect(screen.getByText(/CONSOLE for analyst_jordan/i)).toBeInTheDocument()
    );
  });

  it("shows an error and keeps the login form on invalid credentials", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      text: async () => "unauthorized",
    });

    render(<AuthGate>{() => <div>CONSOLE CONTENT</div>}</AuthGate>);

    await waitFor(() =>
      expect(screen.getByLabelText(/username/i)).toBeInTheDocument()
    );

    fireEvent.change(screen.getByLabelText(/username/i), {
      target: { value: "analyst_jordan" },
    });
    fireEvent.change(screen.getByLabelText(/password/i), {
      target: { value: "wrong" },
    });
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(/invalid username or password/i)
    );
    expect(screen.queryByText("CONSOLE CONTENT")).not.toBeInTheDocument();
  });
});
