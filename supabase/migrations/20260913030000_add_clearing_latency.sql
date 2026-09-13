begin;

alter table clearing.operations
    add column if not exists latency_seconds numeric(10, 3) not null default 0
    check (latency_seconds >= 0);

commit;
