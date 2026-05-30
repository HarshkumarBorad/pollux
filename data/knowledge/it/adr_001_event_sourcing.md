# ADR-001: Event Sourcing for the Billing System

- **Status:** Accepted
- **Date:** 2025-03-14
- **Authors:** Lina Schmidt (Platform), Marc Weber (Billing)

## Context

The Aurora billing system needs to:

- Reconcile usage from multiple sources (compute, storage, network).
- Support late-arriving usage events (up to 48 hours).
- Produce auditable, immutable bills for regulatory compliance.
- Allow replay of bill computation to debug discrepancies.

The previous design used a normalized SQL schema with monthly aggregations. Replaying billing logic against historical data required complex reverse-engineering of intermediate state. A bug in February 2025 took 11 days to fully reconcile across affected customers.

## Decision

We will use **event sourcing** for billing. Every usage event is appended to a per-customer event log; bills are computed by projecting over that log.

- Event store: PostgreSQL with append-only table per customer.
- Projection: read-side materialized views, rebuilt nightly.
- Replay: bills can be reproduced by replaying events against the version of the billing logic in effect at the time.

## Consequences

**Positive:**
- Late-arriving events insert cleanly without re-running aggregations.
- Audit trail is the source of truth.
- Bug fixes in billing logic can be tested by replaying historical events.

**Negative:**
- More storage cost — we keep raw events forever.
- Projection rebuilds are I/O-intensive (mitigated by overnight runs).
- Engineers must learn the event-sourcing model.

## Alternatives considered

- **Append-only ledger in S3** — cheaper storage, but query latency too high for daily reconciliation.
- **Change-data-capture from the old schema** — keeps the old design but adds complexity without buying replayability.

## Migration plan

1. **Dual-write**: bill computation runs against both old SQL schema and new event log for 3 months.
2. **Reconciliation**: compare daily reconciliations; resolve discrepancies.
3. **Cutover**: after 3 months of zero discrepancies, old schema becomes read-only and is eventually archived.
