# Editor de workflows a pantalla completa (rutas) — Diseño

**Fecha:** 2026-06-20
**Estado:** Aprobado
**Servicio:** `packages/web`

## Problema

Crear y editar un workflow ocurre hoy dentro de un `Dialog` modal
(`create-workflow-dialog.tsx`, y un Dialog de edición dentro de
`workflow-detail-client.tsx`). Con el editor de canvas (React Flow) el modal
queda apretado: con muchos nodos no hay espacio para trabajar el grafo.

## Objetivo

Llevar la acción de **modificar** un workflow (crear o editar — NO ver) a su
propia ruta a pantalla completa. "Ver" sigue siendo la página de detalle.

## Decisiones tomadas

- Rutas dedicadas full-screen para crear y editar.
- Una sola página `WorkflowEditorPage` que cubre ambos modos.
- Se elimina el modal de creación y el Dialog de edición inline.

## Rutas

- `/workflows/new` — crear (editor vacío).
- `/workflows/:id/edit` — editar (carga el workflow por id).

(Se mantienen `/workflows`, `/workflows/:id` (ver), `/workflows/:id/runs/:runId`.)

## Componente

`pages/WorkflowEditorPage.tsx` — página full-screen (layout consistente con la
página de detalle: header con back + título) que monta el `WorkflowEditor`
existente en dos modos:

- **create** (sin `id`): editor vacío. Al guardar: `POST /api/workflows` →
  navega a `/workflows/:id` (detalle del nuevo workflow). Cancelar → `/workflows`.
- **edit** (con `id`): fetch del workflow (reusa `normalizeWorkflow`), editor con
  sus valores/nodos. Al guardar: `PUT /api/workflows/:id` → navega a
  `/workflows/:id`. Cancelar → `/workflows/:id`.

El armado del payload `nodes` (id, label, taskName, args, kwargs, queue,
dependsOn, condition, timeoutSeconds, positionX/Y) + campos de schedule —
hoy duplicado en `create-workflow-dialog.tsx` y en `workflow-detail-client.tsx`
— se **consolida** en esta página.

## Wiring

- `WorkflowsPage.tsx`: el botón "Create Workflow" deja de abrir el modal y
  navega a `/workflows/new` (link/navigate).
- `workflow-detail-client.tsx`: el botón "Edit" deja de abrir el Dialog inline y
  navega a `/workflows/:id/edit`.
- `router.tsx`: registrar las dos rutas nuevas.

## Eliminados

- `components/workflows/create-workflow-dialog.tsx`.
- El `Dialog` de edición dentro de `workflow-detail-client.tsx` (la lógica de
  submit migra a la página).

## Testing

- No hay runner de tests para páginas; verificación por `tsc -b --noEmit` +
  `vite build` + manual (consistente con el resto del frontend). El
  `WorkflowEditor` y los helpers ya están cubiertos por vitest.
- Smoke manual: "Create Workflow" abre `/workflows/new` full screen, crear →
  redirige al detalle; en el detalle, "Edit" abre `/workflows/:id/edit` con los
  datos cargados, guardar → vuelve al detalle con los cambios.

## Fuera de alcance (YAGNI)

- Cambios en el backend (los endpoints create/update ya existen).
- Cambios en el `WorkflowEditor`/canvas en sí.
- Confirmación de "descartar cambios" al cancelar (se puede sumar después).
