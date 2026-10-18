/**
 * Frontend Application Configuration.
 *
 * IMPORTANT SECURITY NOTICE:
 * All variables prefixed with `VITE_` are bundled directly into client-side JavaScript.
 * They are completely PUBLIC to anyone inspecting network traffic or the client bundle.
 * NEVER place API keys, private tokens, passwords, or secret credentials in VITE_* variables.
 */

interface AppConfig {
  apiBaseUrl: string;
  appName: string;
}

// Safe environment lookup supporting both Vite client (import.meta.env) and Node server (process.env)
const env =
  (typeof import.meta !== 'undefined' && (import.meta as Record<string, any>).env) ||
  (typeof process !== 'undefined' && process.env) ||
  {};

export const config: AppConfig = {
  apiBaseUrl: (env.VITE_API_BASE_URL as string) || "",
  appName: "AegisPay AI",
};
