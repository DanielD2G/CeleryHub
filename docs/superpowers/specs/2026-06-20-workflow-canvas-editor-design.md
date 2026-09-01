# Editor de workflows tipo canvas (React Flow) — Diseño

**Fecha:** 2026-06-20
**Estado:** Aprobado (pendiente revisión final del usuario)
**Servicio:** `packages/web` (frontend) + cambio menor en `services/celery-gateway` (posiciones)

## Problema

El editor de workflows actual es un **form de tarjetas apiladas** (un editor por
nodo) más un **DAG de preview read-only**. Con 10+ tareas se vuelve scroll
infinito y conectar dependencias por dropdown es tedioso. Falta la fluidez de un
editor de grafo tipo n8n (arrastrar para conectar, acomodar libremente, ver el
flujo).

## Objetivo

Reemplazar el form + el DAG read-only por un **canvas interactivo** construido
con React Flow (`@xyflow/react` v12, core MIT/gratuito — n8n está construido
sobre esta librería). El mismo componente sirve en dos modos: **editable**
(crear/editar) y **read-only** (visualizar runs coloreados por estado).

## Decisiones tomadas

- **El canvas reemplaza** el form de tarjetas (`workflow-form.tsx`,
  `workflow-node-editor.tsx`) y el DAG read-only (`workflow-dag*.tsx`).
- **Persistir posiciones** de nodos (nuevos campos en `WorkflowNode`) + botón
  "auto-ordenar" que re-corre dagre.
- **Vista de run:** mismo canvas en read-only (coloreado por estado) **más** la
  tabla de `nodeRuns` como detalle complementario.
- **Config de nodo:** panel lateral (drawer) a la derecha.
- **Librería:** `@xyflow/react` v12 (MIT). Se mantiene `@dagrejs/dagre` para
  auto-layout y para sembrar posiciones de nodos nuevos.

## Arquitectura

```
WorkflowCanvas (@xyflow/react)
  ├─ Nodos React Flow    ← WorkflowNode[]  (1 nodo RF = 1 WorkflowNode)
  ├─ Aristas React Flow  ← derivadas de dependsOn (source=dep, target=nodo)
  ├─ Drawer de config (derecha)  ← edita el nodo seleccionado (modo editable)
  ├─ Drawer de detalle de run    ← status/result/error (modo read-only)
  ├─ Paleta / "+"  ← agregar nodo (buscador de taskName) + "+" en arista (insertar entre)
  └─ Botón auto-layout (dagre)   ← re-ordena posiciones
```

- **Edición:** arrastrar entre handles crea una dependencia (`dependsOn`);
  arrastrar el nodo mueve su posición; doble-click abre el drawer.
- **Dos modos** en el mismo componente: `editable` y `readOnly`.

## Modelo de datos

Migración Alembic `0005` (encadena sobre `0004`):

- `WorkflowNode`: + `position_x: float | None`, `position_y: float | None`.
- `NodeInput` / `NodeResponse`: + `positionX` / `positionY` (camelCase).
- Frontend `WorkflowNode` type: + `position: { x: number; y: number }`
  (mapeado desde positionX/Y; default vía dagre si faltan).
- Al crear un nodo sin posición (o import sin posiciones) → dagre asigna una
  inicial; el botón auto-layout sobrescribe.
- `NodeRun` **no cambia** (la posición es de la definición; el run read-only usa
  las posiciones del `WorkflowNode`).

## UX del editor (modo editable)

- **Agregar nodo:** botón "+ Tarea" → buscador de `taskName` (sobre
  `knownTaskNames`); el nodo cae en el canvas (posición dagre/centro). "+" sobre
  una arista para **insertar un nodo entre** dos (re-cablea `dependsOn`).
- **Conectar:** arrastrar handle salida de A → entrada de B crea la dep
  (B `dependsOn` A). Borrar arista = quitar la dep.
- **Prevención de ciclos en vivo:** React Flow rechaza una conexión que crearía
  ciclo o self-dep (helper TS compartido `wouldCreateCycle`, misma lógica de
  Kahn). La validación del backend (`_validate_dag`) se mantiene como red de
  seguridad en el save.
- **Config:** doble-click (o click + "editar") abre el drawer con `taskName`,
  args, kwargs, queue, `condition`, `timeoutSeconds`. Reusa los builders
  existentes (`ArgsBuilder`/`KwargsBuilder`/`QueueSelector`).
- **Selección/borrado:** seleccionar nodo(s) + Del; borrar un nodo limpia las
  deps que lo referencian.
- **Guardar:** un submit arma el payload `nodes` con `dependsOn` desde las
  aristas y `positionX/Y` desde el canvas. Mismo endpoint create/update.

## Vista de run (modo read-only)

- El mismo `WorkflowCanvas` en `readOnly`: nodos coloreados por `NodeRun.status`
  (pending/running/succeeded/failed/skipped), aristas hacia nodos activos
  animadas, posiciones tomadas del `WorkflowNode`.
- Click en un nodo → drawer de detalle de run (status, `celeryTaskId` con link a
  la task, timings, error/result).
- Debajo, la **tabla de `nodeRuns`** se mantiene como detalle complementario.
- El refresco en vivo usa el mismo polling/SSE que ya alimenta la página de run.

## Componentes / estructura de archivos

Nuevos:
- `workflow-canvas.tsx` — wrapper de `<ReactFlow>` (modos editable/readOnly),
  maneja nodes/edges state ↔ `WorkflowNode[]`.
- `canvas-node.tsx` — nodo custom (label, taskName, badge de estado, handles).
- `canvas-edge.tsx` — arista custom (con "+" para insertar).
- `node-config-drawer.tsx` — drawer de edición (reusa builders).
- `node-run-drawer.tsx` — drawer de detalle de run (read-only).
- `lib/workflow-graph.ts` — helpers puros: `nodesToFlow` / `flowToNodes`
  (modelo↔React Flow, incl. `dependsOn`↔edges y position), `wouldCreateCycle`,
  auto-layout dagre.

Eliminados:
- `workflow-form.tsx`, `workflow-node-editor.tsx`, `workflow-dag.tsx`,
  `workflow-dag-node.tsx`, `workflow-dag-edge.tsx`.

Adaptados:
- `create-workflow-dialog.tsx`, `import-workflow-dialog.tsx` montan el canvas;
  el import sin posiciones cae en auto-layout.
- `workflow-detail-client.tsx`, `WorkflowDetailPage.tsx`, `WorkflowRunPage.tsx`,
  `workflow-run-history.tsx` usan el canvas (editable/readOnly según el caso) +
  la tabla de nodeRuns.

Dependencia nueva: `@xyflow/react`. Se mantiene `@dagrejs/dagre`.

## Testing

- **Backend:** migración `0005` reversible; `NodeInput`/`NodeResponse` con
  positionX/Y (round-trip create→read); create/update persisten posiciones;
  import sin posiciones no rompe.
- **Frontend (unit):** helpers de `workflow-graph.ts` — `nodesToFlow` /
  `flowToNodes` (`dependsOn`↔edges, position), `wouldCreateCycle` (ciclo /
  self-dep), auto-layout asigna posición a todos los nodos.
- **Frontend (componente):** agregar nodo, conectar (crea dep), conexión que
  haría ciclo rechazada, drawer edita y persiste en el payload, modo readOnly
  colorea por estado. (`@testing-library/react`, montando el provider de React
  Flow.)
- **Build:** `tsc -b --noEmit` 0 errores + `vite build`.

## Fuera de alcance (YAGNI)

- React Flow Pro / features pagas.
- Mini-mapa, undo/redo, multi-selección avanzada, copy/paste de subgrafos
  (se pueden sumar después).
- Cambios en el engine o en la persistencia de eventos.
- Migración de datos: los workflows existentes sin posición caen en auto-layout
  (no requiere migrar datos).
