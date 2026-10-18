import { defineConfig } from "drizzle-kit";
import * as dotenv from "dotenv";

dotenv.config();

// Prefer the local POSTGRES_* names used in .env; fall back to the Cloud SQL
// SQL_*/SQL_ADMIN_* names for managed deployments.
const sqlHost = process.env.POSTGRES_HOST || process.env.SQL_HOST;
const sqlDbName = process.env.POSTGRES_DB || process.env.SQL_DB_NAME;
const user = process.env.POSTGRES_USER || process.env.SQL_ADMIN_USER || process.env.SQL_USER;
const password = process.env.POSTGRES_PASSWORD || process.env.SQL_ADMIN_PASSWORD || process.env.SQL_PASSWORD;
const port = Number(process.env.POSTGRES_PORT || process.env.SQL_PORT || 5432);

if (!sqlHost) {
  throw new Error("POSTGRES_HOST (or SQL_HOST) must be set in environment variables.");
}
if (!sqlDbName) {
  throw new Error("POSTGRES_DB (or SQL_DB_NAME) must be set in environment variables.");
}
if (!user) {
  throw new Error("POSTGRES_USER (or SQL_ADMIN_USER) must be set in environment variables.");
}
if (!password) {
  throw new Error("POSTGRES_PASSWORD (or SQL_ADMIN_PASSWORD) must be set in environment variables.");
}

export default defineConfig({
  schema: "./src/db/schema.ts",
  out: "./drizzle",
  dialect: "postgresql",
  schemaFilter: ["public"],
  dbCredentials: {
    host: sqlHost,
    port,
    user: user,
    password: password,
    database: sqlDbName,
    ssl: false,
  },
  verbose: true,
});
