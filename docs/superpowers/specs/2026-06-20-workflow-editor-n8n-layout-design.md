# Editor de workflows: layout estilo n8n (canvas full + topbar) — Diseño

**Fecha:** 2026-06-20
**Estado:** Aprobado
**Servicio:** `packages/web`

## Problema

El `WorkflowEditor` usa una grilla de dos columnas: la columna izquierda (un
"sidebar") tiene el formulario de datos del workflow (nombre, descripción,
schedule, max runs, enabled, guardar) y la derecha el canvas. Eso achica el
canvas. El usuario quiere el layout de n8n: **canvas a todo el ancho** y la
metadata del workflow en una **barra superior** + un panel de settings, no en
una columna lateral.

## Objetivo

Reestructurar el `WorkflowEditor` a un layout vertical estilo n8n: una topbar
arriba y el canvas ocupando todo el ancho y alto debajo. La config del workflow
se mueve a la topbar (nombre inline, enabled) + un drawer de Settings (schedule,
descripción, max runs).

## Decisiones tomadas

- Canvas a todo el ancho/alto; se elimina la columna-formulario izquierda.
- Topbar con nombre editable inline + toggle Enabled (estilo Inactive/Active de
  n8n).
- Resto de la config (descripción, schedule, max runs) en un **Settings drawer**.
- El panel de config de **nodo** (`NodeConfigDrawer`) se mantiene igual.
- Sin cambios de backend.

## Layout

```
┌───────────────────────────────────────────────────────────────┐
│ TOPBAR:  ← back   [Nombre inline]   Enabled ⏻   + Tarea  ⌗Auto │
│                                          Settings ⚙   Guardar  │
├───────────────────────────────────────────────────────────────┤
│                                                                 │
│                      CANVAS (full width/height)                 │
│                                                                 │
└───────────────────────────────────────────────────────────────┘
   (Settings drawer y NodeConfigDrawer son overlays — no afectan el layout)
```

`WorkflowEditor` pasa de `form > grid 2-col` a `flex-col h-full`:
- **Topbar** (altura fija): back, nombre editable inline (Input sin chrome /
  estilo título), toggle Enabled, acciones del canvas (**+ Tarea**,
  **Auto-ordenar**), botón **Settings** (abre el drawer), botón **Guardar**
  (con estado submitting + validación: nombre requerido, ≥1 nodo). El error de
  submit se muestra cerca del botón Guardar (toast/inline).
- **Canvas** (`flex-1`, min-h-0): `WorkflowCanvas` a todo el espacio.

## Settings drawer (nuevo)

Un `Sheet` (lado, reusa el primitive existente) abierto por el botón Settings,
con los controles que hoy están en la columna izquierda **movidos tal cual**:
- Descripción (textarea).
- Schedule: `Tabs` none / interval / cron (con sus inputs).
- Max run count.
(El toggle Enabled vive en la topbar, no acá — estilo n8n.)

## Componentes / archivos

- `components/workflows/workflow-editor.tsx`: reestructurar el render a
  topbar + canvas full; extraer los controles de schedule/descripción/maxRun a
  un drawer. Mantener todo el state y la lógica de submit/add/insert/auto-layout.
  Nuevo prop `onBack?: () => void` para el botón back de la topbar.
- `components/workflows/workflow-settings-drawer.tsx` (nuevo): el Sheet con
  descripción + schedule + maxRun, controlado por props (valores + setters o un
  objeto values + onChange).
- `pages/WorkflowEditorPage.tsx`: dejar de renderizar su header propio (back +
  título); pasar `onBack={() => navigate(backTo)}` al `WorkflowEditor`. El
  contenedor sigue `h-screen` para que el canvas use toda la altura.
- `NodeConfigDrawer`: sin cambios.

## Testing

- Sin runner de páginas: verificación por `tsc -b --noEmit` + `vite build` +
  manual. `WorkflowEditor`/helpers ya cubiertos por vitest (sigue verde).
- Smoke manual: crear/editar abre con canvas full; nombre editable en la topbar;
  Settings abre el drawer con schedule/descr/maxRun; Enabled toggle en topbar;
  guardar persiste todo igual que antes.

## Fuera de alcance (YAGNI)

- Cambios en el `NodeConfigDrawer` (config de nodo) — se mantiene.
- Cambios de backend.
- Tabs Editor/Executions, Share, tags, etc. de n8n (no pedidos).
- Mini-mapa / otras features de canvas.
