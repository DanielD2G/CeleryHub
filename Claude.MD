Cuando hagas un commit no añadas co authored
CeleryHub

  CeleryHub es un dashboard web de monitoreo en tiempo real para clusters de https://docs.celeryq.dev/.
  Permite observar workers, inspeccionar tareas, enviar jobs, gestionar colas y configurar tareas periódicas
  (beat schedules) desde el navegador.

  ---
  Stack

  ┌──────────┬───────────────────────────────────────────────────────────────────────────┐
  │   Capa   │                              Tecnologías                                  │
  ├──────────┼───────────────────────────────────────────────────────────────────────────┤
  │ Frontend │ React 19, Vite, React Router v7, shadcn/ui, Recharts, Tailwind CSS v4     │
  ├──────────┼───────────────────────────────────────────────────────────────────────────┤
  │ Backend  │ FastAPI (Python), Celery, SQLAlchemy 2.0 async, Pydantic, redis.asyncio   │
  ├──────────┼───────────────────────────────────────────────────────────────────────────┤
  │ Database │ SQLite (aiosqlite), migratable a PostgreSQL                               │
  ├──────────┼───────────────────────────────────────────────────────────────────────────┤
  │ Broker   │ Redis                                                                     │
  ├──────────┼───────────────────────────────────────────────────────────────────────────┤
  │ Monorepo │ packages/web (React SPA) + services/celery-gateway (FastAPI backend)      │
  └──────────┴───────────────────────────────────────────────────────────────────────────┘

  ---
  Colores

  El tema usa oklch y es completamente neutral/monocromático (escala de grises), configurado via shadcn/ui:

  Light mode:
  - background: blanco casi puro (oklch(0.98 0 0))
  - foreground: negro casi puro (oklch(0.145 0 0))
  - primary: negro oscuro (oklch(0.205 0 0))
  - muted-foreground: gris medio (oklch(0.556 0 0))
  - destructive: rojo (oklch(0.577 0.245 27.325))

  Dark mode:
  - background: negro oscuro (oklch(0.145 0 0))
  - foreground: blanco casi puro (oklch(0.985 0 0))
  - primary: gris claro (oklch(0.922 0 0))
  - destructive: rojo más claro (oklch(0.704 0.191 22.216))

  Charts (colores con cromatismo):

  ┌─────────┬──────────────────────┬────────────────────┐
  │  Token  │        Light         │ Descripción aprox. │
  ├─────────┼──────────────────────┼────────────────────┤
  │ chart-1 │ oklch(0.60 0.12 250) │ Azul               │
  ├─────────┼──────────────────────┼────────────────────┤
  │ chart-2 │ oklch(0.65 0.12 165) │ Verde/teal         │
  ├─────────┼──────────────────────┼────────────────────┤
  │ chart-3 │ oklch(0.60 0.11 290) │ Púrpura            │
  ├─────────┼──────────────────────┼────────────────────┤
  │ chart-4 │ oklch(0.72 0.11 80)  │ Amarillo/dorado    │
  ├─────────┼──────────────────────┼────────────────────┤
  │ chart-5 │ oklch(0.65 0.11 20)  │ Rojo/coral         │
  └─────────┴──────────────────────┴────────────────────┘

  En resumen: la UI es monocromática (blanco/negro/grises) con color reservado para los gráficos de Recharts
  y el estado destructive (rojo).


En Python. Debes asegurarte de typear todo. Usar _ para variables privadas. Y mantener la calidad del codigo reusando el codigo
