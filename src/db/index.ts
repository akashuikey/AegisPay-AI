import { drizzle } from 'drizzle-orm/node-postgres';
import { Pool } from 'pg';
import * as schema from './schema.ts';

declare global {
  // eslint-disable-next-line no-var
  var _postgresPool: Pool | undefined;
}

// Connection settings. Supports both the local POSTGRES_* names used in .env and
// the Cloud SQL SQL_* names, plus an explicit DATABASE_URL override.
const connectionString = process.env.DATABASE_URL || undefined;
const host = process.env.POSTGRES_HOST || process.env.SQL_HOST || '';
const user = process.env.POSTGRES_USER || process.env.SQL_USER || '';
const password = process.env.POSTGRES_PASSWORD || process.env.SQL_PASSWORD || '';
const database = process.env.POSTGRES_DB || process.env.SQL_DB_NAME || '';
const port = Number(process.env.POSTGRES_PORT || process.env.SQL_PORT || 5432);

/**
 * True only when enough configuration is present to attempt a connection. When
 * false, DB-backed endpoints should skip the query instead of letting `pg` throw
 * (e.g. "SASL: client password must be a string") on every request.
 */
export const isDbConfigured = Boolean(connectionString || (host && user && password && database));

export const createPool = (): Pool => {
  if (!global._postgresPool) {
    global._postgresPool = new Pool(
      connectionString
        ? { connectionString, max: 10, connectionTimeoutMillis: 15000 }
        : { host, user, password, database, port, max: 10, connectionTimeoutMillis: 15000 }
    );

    global._postgresPool.on('error', (err) => {
      console.error('Unexpected error on idle SQL pool client:', err.message);
    });
  }
  return global._postgresPool;
};

export const pool = createPool();
export const db = drizzle(pool, { schema });

/**
 * Idempotently create the app's own (aegis_-prefixed) tables so DB persistence
 * works without a manual migration step and without colliding with the legacy
 * Python/Alembic tables that share this database. Best-effort: callers ignore
 * failures (the in-memory store remains the source of truth for the demo).
 */
export async function ensureSchema(): Promise<void> {
  if (!isDbConfigured) return;
  await pool.query(`
    CREATE TABLE IF NOT EXISTS aegis_users (
      id serial PRIMARY KEY,
      uid text NOT NULL UNIQUE,
      email text NOT NULL,
      display_name text,
      created_at timestamp DEFAULT now()
    );
    CREATE TABLE IF NOT EXISTS aegis_transactions (
      id serial PRIMARY KEY,
      tx_id text NOT NULL UNIQUE,
      user_id integer REFERENCES aegis_users(id),
      recipient_name text NOT NULL,
      recipient_upi text NOT NULL,
      amount real NOT NULL,
      purpose text,
      check_reason text,
      risk_score integer DEFAULT 0,
      risk_level text DEFAULT 'LOW',
      verification_status text DEFAULT 'PENDING',
      has_coercion boolean DEFAULT false,
      created_at timestamp DEFAULT now()
    );
    CREATE TABLE IF NOT EXISTS aegis_audit_logs (
      id serial PRIMARY KEY,
      tx_id text NOT NULL,
      decision_action text NOT NULL,
      policy_reason text,
      created_at timestamp DEFAULT now()
    );
  `);
}
