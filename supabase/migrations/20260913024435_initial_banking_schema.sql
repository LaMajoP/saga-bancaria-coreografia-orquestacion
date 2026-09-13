begin;

  create extension if not exists pgcrypto;

  create schema if not exists gateway;
  create schema if not exists account;
  create schema if not exists risk;
  create schema if not exists clearing;
  create schema if not exists saga;

  /*
  ============================================================
  API GATEWAY
  Reemplaza el registro actual que vive solo en memoria.
  ============================================================
  */

  create table if not exists gateway.transfers (
      transfer_id uuid primary key,
      idempotency_key uuid not null unique,
      request_fingerprint char(64) not null,
      status text not null default 'RECIBIDA' check (
          status in (
              'RECIBIDA',
              'EN_PROCESO',
              'CONFIRMADA',
              'RECHAZADA_FONDOS',
              'RECHAZADA_RIESGO',
              'RECHAZADA_RED',
              'COMPENSANDO',
              'COMPENSADA',
              'FALLIDA'
          )
      ),
      source_account_id varchar(64) not null,
      destination_account_id varchar(64) not null,
      amount bigint not null check (amount > 0),
      currency char(3) not null default 'COP'
          check (currency = upper(currency)),
      force_risk_failure boolean not null default false,
      force_clearing_timeout boolean not null default false,
      error_code text,
      message text,
      created_at timestamptz not null default now(),
      updated_at timestamptz not null default now(),
      check (source_account_id <> destination_account_id)
  );

  create index if not exists transfers_status_created_at_idx
      on gateway.transfers (status, created_at desc);

  /* Permite guardar la entrega pendiente hacia Orquestación o Coreografía. */
  create table if not exists gateway.transfer_outbox (
      outbox_id uuid primary key default gen_random_uuid(),
      transfer_id uuid not null unique
          references gateway.transfers(transfer_id) on delete
          cascade,
      saga_mode text not null check (saga_mode in
      ('ORCHESTRATION', 'CHOREOGRAPHY')),
      event_type text not null default 'TransferRequested',
      payload jsonb not null,
      delivery_status text not null default 'PENDING'
          check (delivery_status in ('PENDING', 'DELIVERED',
          'FAILED')),
      attempt_count integer not null default 0 check
      (attempt_count >= 0),
      last_error text,
      created_at timestamptz not null default now(),
      delivered_at timestamptz
  );

  /*
  ============================================================
  ACCOUNT & LEDGER SERVICE
  Migración directa de las dos tablas SQLite actuales.
  ============================================================
  */

  create table if not exists account.accounts (
      account_id varchar(64) primary key,
      balance bigint not null check (balance >= 0),
      currency char(3) not null default 'COP'
          check (currency = upper(currency)),
      created_at timestamptz not null default now(),
      updated_at timestamptz not null default now()
  );

  create table if not exists account.ledger_entries (
      operation_id uuid primary key,
      transfer_id uuid not null,
      account_id varchar(64) not null
          references account.accounts(account_id),
      operation text not null check (
          operation in (
              'debit',
              'credit',
              'debit_compensate',
              'credit_compensate'
          )
      ),
      amount bigint not null check (amount > 0),
      balance_after bigint not null check (balance_after >= 0),
      status text not null check (
          status in ('DEBITED', 'COMPLETED', 'COMPENSATED')
      ),
      compensated boolean not null default false,
      created_at timestamptz not null default now(),
      unique (transfer_id, account_id, operation)
  );

  create index if not exists ledger_entries_transfer_id_idx
      on account.ledger_entries (transfer_id);

  -- Cuentas demostrativas que hoy crea SQLite.
  insert into account.accounts (account_id, balance, currency)
  values
      ('ACC-001', 1500000, 'COP'),
      ('ACC-002', 1000000, 'COP'),
      ('ACC-003', 100000, 'COP')
  on conflict (account_id) do nothing;

  /*
  ============================================================
  RISK SERVICE
  Aún no tiene código, pero la tabla queda lista.
  ============================================================
  */

  create table if not exists risk.evaluations (
      evaluation_id uuid primary key default gen_random_uuid(),
      transfer_id uuid not null unique,
      source_account_id varchar(64) not null,
      destination_account_id varchar(64) not null,
      amount bigint not null check (amount > 0),
      force_failure boolean not null default false,
      status text not null check (
          status in ('RISK_APPROVED', 'RISK_REJECTED',
          'COMPENSATED')
      ),
      error_code text,
      message text,
      compensated boolean not null default false,
      created_at timestamptz not null default now(),
      updated_at timestamptz not null default now()
  );

  /*
  ============================================================
  CLEARING SERVICE
  Aún no tiene código, pero la tabla queda lista.
  ============================================================
  */

  create table if not exists clearing.operations (
      operation_id uuid primary key default gen_random_uuid(),
      transfer_id uuid not null unique,
      source_account_id varchar(64) not null,
      destination_account_id varchar(64) not null,
      amount bigint not null check (amount > 0),
      force_timeout boolean not null default false,
      status text not null check (
          status in ('COMPLETED', 'REJECTED_NETWORK',
          'COMPENSATED')
      ),
      error_code text,
      message text,
      compensated boolean not null default false,
      created_at timestamptz not null default now(),
      updated_at timestamptz not null default now()
  );

  /*
  ============================================================
  SAGA
  Pertenece a Persona 2; no tiene llaves foráneas hacia otros
  schemas para respetar el aislamiento entre microservicios.
  ============================================================
  */

  create table if not exists saga.executions (
      transfer_id uuid primary key,
      implementation text not null check (
          implementation in ('ORCHESTRATION', 'CHOREOGRAPHY')
      ),
      status text not null,
      current_step text,
      error_code text,
      message text,
      created_at timestamptz not null default now(),
      updated_at timestamptz not null default now()
  );

commit;