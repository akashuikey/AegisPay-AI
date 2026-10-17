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

export const config: AppConfig = {
  apiBaseUrl: import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000",
  appName: "AegisPay AI",
};
