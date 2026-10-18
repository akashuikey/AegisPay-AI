import { integer, pgTable, serial, text, timestamp, real, boolean } from 'drizzle-orm/pg-core';
import { relations } from 'drizzle-orm';

export const users = pgTable('users', {
  id: serial('id').primaryKey(),
  uid: text('uid').notNull().unique(), // Firebase Auth UID
  email: text('email').notNull(),
  displayName: text('display_name'),
  createdAt: timestamp('created_at').defaultNow(),
});

export const transactions = pgTable('transactions', {
  id: serial('id').primaryKey(),
  txId: text('tx_id').notNull().unique(),
  userId: integer('user_id').references(() => users.id),
  recipientName: text('recipient_name').notNull(),
  recipientUpi: text('recipient_upi').notNull(),
  amount: real('amount').notNull(),
  purpose: text('purpose'),
  checkReason: text('check_reason'),
  riskScore: integer('risk_score').default(0),
  riskLevel: text('risk_level').default('LOW'),
  verificationStatus: text('verification_status').default('PENDING'),
  hasCoercion: boolean('has_coercion').default(false),
  createdAt: timestamp('created_at').defaultNow(),
});

export const auditLogs = pgTable('audit_logs', {
  id: serial('id').primaryKey(),
  txId: text('tx_id').notNull(),
  decisionAction: text('decision_action').notNull(),
  policyReason: text('policy_reason'),
  createdAt: timestamp('created_at').defaultNow(),
});

export const usersRelations = relations(users, ({ many }) => ({
  transactions: many(transactions),
}));

export const transactionsRelations = relations(transactions, ({ one }) => ({
  user: one(users, {
    fields: [transactions.userId],
    references: [users.id],
  }),
}));
