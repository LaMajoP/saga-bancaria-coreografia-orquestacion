begin;

/*
============================================================
SCHEMA SAGA — Persona 2
Sin llaves foráneas hacia gateway/account/risk/clearing: el
aislamiento entre microservicios es criterio evaluado (5).
La correlación entre dominios es siempre por transfer_id.
============================================================
*/

create schema if not exists saga;

/*
------------------------------------------------------------
1. EJECUCIONES
Una fila por saga. 'status' guarda el desenlace y
'compensation_status' la evidencia de la marcha atrás: son
ortogonales, de modo que CP-03 puede reportar a la vez
REJECTED_RISK y COMPENSATED.
------------------------------------------------------------
*/

alter table saga.executions
    add column if not exists compensation_status text not null default 'NOT_REQUIRED',
    add column if not exists source_account_id varchar(64),
    add column if not exists destination_account_id varchar(64),
    add column if not exists amount bigint,
    add column if not exists currency char(3) not null default 'COP',
    add column if not exists force_risk_failure boolean not null default false,
    add column if not exists force_clearing_timeout boolean not null default false,
    add column if not exists started_at timestamptz not null default now(),
    add column if not exists finished_at timestamptz;

do $$
begin
    if not exists (
        select 1 from pg_constraint where conname = 'executions_status_check'
    ) then
        alter table saga.executions add constraint executions_status_check check (
            status in (
                'PENDING', 'DEBITED', 'RISK_APPROVED', 'CLEARING_PENDING',
                'COMPLETED', 'COMPENSATING',
                'REJECTED_FUNDS', 'REJECTED_RISK', 'REJECTED_NETWORK', 'FAILED'
            )
        );
    end if;

    if not exists (
        select 1 from pg_constraint where conname = 'executions_compensation_status_check'
    ) then
        alter table saga.executions add constraint executions_compensation_status_check check (
            compensation_status in (
                'NOT_REQUIRED', 'COMPENSATING', 'COMPENSATED', 'COMPENSATION_FAILED'
            )
        );
    end if;

    if not exists (
        select 1 from pg_constraint where conname = 'executions_current_step_check'
    ) then
        alter table saga.executions add constraint executions_current_step_check check (
            current_step is null or current_step in ('DEBIT', 'RISK', 'CLEARING', 'CREDIT')
        );
    end if;
end $$;

create index if not exists executions_status_idx
    on saga.executions (status, started_at desc);

create index if not exists executions_implementation_idx
    on saga.executions (implementation, started_at desc);

/*
------------------------------------------------------------
2. BITÁCORA DE PASOS
Auditoría exigida por CP-04. Una fila por paso lógico; los
reintentos incrementan 'attempt' en lugar de duplicar filas,
para que el orden de reversa se lea sin ruido.
'sequence' es el orden real de ejecución: las compensaciones
reciben números crecientes, de modo que ordenar por sequence
demuestra que la reversa ocurrió en orden inverso.
------------------------------------------------------------
*/

create table if not exists saga.saga_steps (
    step_id uuid primary key default gen_random_uuid(),
    transfer_id uuid not null,
    sequence integer not null check (sequence > 0),
    step_name text not null check (step_name in ('DEBIT', 'RISK', 'CLEARING', 'CREDIT')),
    kind text not null check (kind in ('ACTION', 'COMPENSATION')),
    service text not null,
    operation text not null,
    status text not null check (
        status in ('EXECUTED', 'FAILED', 'SKIPPED', 'COMPENSATED', 'COMPENSATION_FAILED')
    ),
    attempt integer not null default 1 check (attempt > 0),
    error_code text,
    message text,
    duration_ms integer check (duration_ms >= 0),
    request jsonb,
    response jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (transfer_id, step_name, kind)
);

create index if not exists saga_steps_transfer_idx
    on saga.saga_steps (transfer_id, sequence);

/*
------------------------------------------------------------
3. EVENT STORE DE LA COREOGRAFÍA
Formato del contrato §12. Persistir todo evento publicado da
trazabilidad sin depender de que RabbitMQ conserve historial.
------------------------------------------------------------
*/

create table if not exists saga.saga_events (
    event_id uuid primary key,
    event_type text not null,
    transfer_id uuid not null,
    payload jsonb not null default '{}'::jsonb,
    occurred_at timestamptz not null,
    recorded_at timestamptz not null default now()
);

create index if not exists saga_events_transfer_idx
    on saga.saga_events (transfer_id, occurred_at);

create index if not exists saga_events_type_idx
    on saga.saga_events (event_type, occurred_at desc);

/*
------------------------------------------------------------
4. DEDUPLICACIÓN DE CONSUMO
Segunda barrera de idempotencia (CP-05). RabbitMQ garantiza
at-least-once; esta tabla convierte eso en efecto exactly-once
por participante.
------------------------------------------------------------
*/

create table if not exists saga.processed_events (
    consumer text not null,
    event_id uuid not null,
    transfer_id uuid not null,
    processed_at timestamptz not null default now(),
    primary key (consumer, event_id)
);

create index if not exists processed_events_transfer_idx
    on saga.processed_events (transfer_id);

commit;
