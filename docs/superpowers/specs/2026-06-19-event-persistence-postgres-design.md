# Persistencia de eventos en PostgreSQL — Diseño

**Fecha:** 2026-06-19
**Estado:** Aprobado (pendiente revisión final del usuario)
**Servicio:** `services/celery-gateway`

## Problema

Hoy los eventos de Celery que llegan por Redis pub/sub (`/{db}.celeryev/*`) se
procesan en `event_collector._persist_event()` y se guardan **solo en Redis**
como estado derivado y efímero (hashes con TTL, un zset `completed` capado a
2000). No existe un historial durable: todo lo que excede el TTL o el cap se
pierde, igual que en Flower. La meta es **preservar todos los eventos
escuchados** en una base persistente, soportando millones de registros.

## Decisiones tomadas

- **Migración total a PostgreSQL**, sin retrocompatibilidad con los datos
  SQLite actuales. Se rediseña el esquema nativo (JSONB, tipos reales) y se
  elimina SQLite + las migraciones a mano.
- **Arquitectura de dos capas:** Redis sigue siendo la capa caliente (vista en
  vivo, SSE, tareas activas — sin cambios). Postgres es el log durable
  append-only de todos los eventos.
- **Modelo append-only:** cada evento escuchado es una fila inmutable (log
  crudo), no un upsert de estado por tarea.
- **Retención por ventana:** default 30 días, configurable por env var y desde
  la UI. Particionado diario para dropear lo viejo instantáneamente.
- **Escritura resiliente:** buffer en Redis Stream + flush en batch a Postgres
  (at-least-once, sin pérdida, no bloquea el SSE).
- **Postgres externo** vía `DATABASE_URL` (docker-compose / gestionado).
- **Postgres plano** con particionado nativo (sin TimescaleDB), para no atar el
  despliegue a una imagen específica.

## Arquitectura

```
Eventos de Celery (Redis pub/sub  /{db}.celeryev/*)
        │
        ▼
  event_collector._persist_event()
        │
        ├─► Redis (capa CALIENTE — SIN cambios)
        │     active-tasks, completed zset, task meta, payloads — vista en vivo + SSE
        │
        └─► Redis Stream  "celeryhub:events:stream"   (buffer durable)
                  │
                  ▼
        event_persister (asyncio.Task, consumer group)
                  │  lee en lotes (≈500 / 1s), XACK tras commit
                  ▼
            PostgreSQL  ──► tabla `celery_events` (append-only, partición diaria)
```

- El collector **no toca Postgres directo**: solo hace `XADD` al stream (barato,
  no bloquea el SSE).
- Un nuevo `event_persister` consume el stream en lotes y hace bulk-insert. Si
  Postgres cae, los eventos quedan pending en el stream y se reintentan
  → **at-least-once, sin pérdida**.

## Modelo de datos

Migración total a Postgres (driver `asyncpg`). Las tablas actuales
(`workflows`, `workflow_runs`, `step_runs`, `task_runs`) se recrean nativas
(JSON→`JSONB`, tipos reales). Se adopta **Alembic** para migraciones; se elimina
`_run_migrations` y `create_all`.

### Tabla `celery_events` (nueva)

Standalone, **sin FK** — la mayoría de eventos no son de workflows; es el log
crudo de todo lo que se escucha.

```
celery_events  (PARTITION BY RANGE (event_time), partición diaria)
  id            bigint identity
  event_uid     text          NOT NULL   -- hash(task_id|event_type|timestamp) para dedup
  event_time    timestamptz   NOT NULL   -- del campo timestamp del evento
  event_type    text          NOT NULL   -- task-sent|received|started|succeeded|failed|revoked|...
  task_id       text                     -- uuid de la tarea (nullable: worker events)
  task_name     text
  hostname      text                     -- worker
  queue         text
  runtime       double precision
  result        text
  exception     text
  traceback     text
  payload       jsonb         NOT NULL   -- evento crudo completo (args, kwargs, y todo lo demás)
  ingested_at   timestamptz   NOT NULL default now()

  UNIQUE (event_uid, event_time)         -- dedup idempotente; incluye clave de partición
  índices: (event_time), (task_id), (task_name, event_time), (event_type, event_time)
```

Columnas tipadas para lo que se filtra seguido; `payload jsonb` preserva el
evento entero para no perder nada.

### Tabla `settings` (nueva)

Clave/valor para configuración runtime editable desde la UI (p. ej. la ventana
de retención).

```
settings
  key    text  primary key
  value  text  NOT NULL
```

## Camino de escritura

- **Collector:** dentro de `_persist_event`, tras los writes a Redis, un
  `XADD celeryhub:events:stream` con los campos del evento parseado. `MAXLEN ~ N`
  aproximado como techo de seguridad del buffer.
- **event_persister** (`services/event_persister.py`):
  - Consumer group `celeryhub-persisters`. Bucle:
    `XREADGROUP COUNT 500 BLOCK 1000`.
  - Mapea cada entry a fila, `INSERT` en lote (`executemany`/`COPY`), commit,
    luego `XACK`.
  - Si el `INSERT` falla → no hace `XACK` → reintenta con backoff exponencial
    (mismo patrón que el collector).
  - Al arrancar procesa primero los **pending** (lo que quedó sin ack tras una
    caída previa).
- **Idempotencia:** at-least-once puede reinsertar tras un crash entre commit y
  XACK. Se resuelve con `event_uid` (hash determinístico
  `task_id|event_type|timestamp`) + `UNIQUE` + `INSERT ... ON CONFLICT DO NOTHING`.

## Retención

- **Particiones diarias** en `celery_events`. Creación adelantada de las
  próximas N particiones; borrado de las más viejas que la ventana.
- Job de retención: `asyncio.Task` que tickea (≈1/hora) y dropea las particiones
  cuyo día < `now - retention_days`. Dropear partición = instantáneo, sin
  `DELETE` ni vacuum.
- `retention_days`: default 30, override por env var, override por UI (tabla
  `settings`, leído en cada tick).

## Migración de código y despliegue

- `db/__init__.py`: engine a `postgresql+asyncpg://` desde `DATABASE_URL`. Se
  eliminan pragmas SQLite, `create_all` y `_run_migrations`.
- **Alembic**: migración inicial con todas las tablas + funciones/partición de
  `celery_events`. Sin retrocompat con datos viejos.
- `config.py`: nuevas settings `database_url`,
  `celeryhub_events_retention_days`, `celeryhub_events_stream_maxlen`.
- `docker-compose`: servicio `postgres` + `DATABASE_URL`. README/`.env.example`
  actualizados.
- Dependencias: `+asyncpg`, `+alembic`; `-aiosqlite`.

## API / UI

- `GET /api/events` — consulta del log histórico con filtros (`task_id`,
  `task_name`, `event_type`, rango de tiempo) y paginación keyset sobre
  `event_time`.
- `GET/PUT /api/settings/retention` — ventana configurable desde la UI.
- La vista en vivo sigue saliendo de Redis/SSE como hoy — no cambia.

## Testing

- **Unit:** mapeo evento→fila, dedup/`event_uid`, lógica de cómputo de
  particiones a dropear.
- **Service/integración:** Postgres efímero (testcontainers o `postgres` de
  compose) — flujo XADD→persister→INSERT, idempotencia tras reintento,
  retención dropeando particiones, endpoint `/api/events` con filtros.
- **Buffer:** simular Postgres caído → eventos se acumulan en el stream → se
  recuperan al volver.

## Fuera de alcance (YAGNI)

- TimescaleDB / compresión / continuous aggregates.
- Archivado frío (Parquet/S3).
- Vista de estado-por-tarea derivada del log (Redis ya cubre la vista viva).
- Retrocompatibilidad / migración de datos desde SQLite.
