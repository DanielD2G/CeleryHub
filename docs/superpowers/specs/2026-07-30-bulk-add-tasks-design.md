# Bulk add tasks — multi-select con auto-wiring

**Fecha:** 2026-07-30
**Estado:** diseño aprobado

## Problema

Armar un fan-in (N tareas que corren antes de una final) es prohibitivamente lento en el
editor actual. Para el caso real —20 tasks distintas, cada una con sus propios args, todas
previas a un nodo final— hoy hacen falta:

| # | Fricción | Costo actual |
|---|---|---|
| a | crear 20 nodos | 20 clicks en `+ Tarea` |
| b | elegir la task y los args de cada una | 20 viajes al drawer, cerrando y buscando el nodo en el canvas cada vez |
| c | conectar las 20 al nodo final | 20 arrastres de handle a handle |

`c` es la peor: arrastrar 20 edges a mano es tedioso y propenso a error.

## Objetivo

Agregar N tareas y colgarlas de un nodo final en **una sola operación**, y después poder
configurar los args de las N sin volver al canvas.

Fuera de alcance (evaluado y descartado por ahora): pegar una lista de texto con sintaxis
de args, y duplicar nodo (`⌘D`). Con este diseño aportan poco y suman superficie.

## Arquitectura

Cuatro piezas. La lógica de creación/cableado vive en funciones puras en `workflow-graph.ts`
para poder testearla: el proyecto no tiene jsdom, así que nada que dependa del DOM es testeable.

| Archivo | Cambio |
|---|---|
| `lib/workflow-graph.ts` | nueva `applyAddedTasks()` (pura) |
| `components/workflows/add-tasks-dialog.tsx` | **nuevo** — el diálogo de selección múltiple |
| `components/workflows/workflow-editor.tsx` | `+ Tarea` abre el diálogo; nuevo `handleAddTasks()` |
| `components/workflows/node-config-drawer.tsx` | header con `‹ i/total ›` y atajos `⌘↓`/`⌘↑` |

No hace falta calcular posiciones para los nodos nuevos: nacen con `position: null` y el
editor corre auto-layout sobre todo el grafo en el mismo paso, así que dagre les asigna la
posición definitiva antes de que se rendericen. Cualquier grilla que calculáramos se pisaría
un instante después.

### `applyAddedTasks(nodes, taskNames, connectTo)`

Función pura. `connectTo` es `{ kind: "none" }`, `{ kind: "node", id }` o `{ kind: "new" }`.

Devuelve `{ nodes, newIds, focusId }`:

- Un nodo nuevo por cada `taskName`, con `label: ""` (el canvas ya hereda el taskName vía
  `nodeDisplayLabel`), `dependsOn: "[]"`, `position: null`, y el resto de los defaults de
  `_blankNode`.
- `kind: "node"` → el nodo `id` recibe los ids nuevos en su `dependsOn`. Los nodos nuevos
  quedan como dependencias suyas, o sea corren **antes** que él.
- `kind: "new"` → crea además un nodo final vacío (`taskName: ""`) cuyo `dependsOn` son los
  N ids nuevos. `focusId` apunta al primer nodo nuevo, no al final.
- `kind: "none"` → los N quedan sueltos.
- Nunca muta los nodos existentes: devuelve copias.

Un `taskName` que ya existe en el grafo se agrega igual: repetir la misma task con args
distintos es un caso válido.

## El diálogo

Reemplaza al `+ Tarea` del topbar (mismo botón, mismo lugar).

**Búsqueda** con autofocus arriba, filtrando `knownTaskNames` de `useCelery()`. Debajo, lista
scrolleable; click en una fila la togglea, con un check a la izquierda. `Enter` agrega la
primera coincidencia y limpia la búsqueda — con eso se cargan 20 tipeando `frav`⏎ `garb`⏎
`musi`⏎ sin tocar el mouse, que es lo que vuelve la operación amena.

Si la búsqueda no matchea nada, aparece `+ Usar «X» como task custom`, mismo comportamiento
que el drawer hoy.

Arriba de la búsqueda, chips con las tasks seleccionadas y una X por chip.

**Selector "Conectar a"**, con tres tipos de opción:

- `Ninguno`
- un item por nodo existente, mostrando su `nodeDisplayLabel()`
- `+ Nodo nuevo después de todas`

Default: el nodo que estuviera seleccionado en el canvas; si no hay ninguno, `Ninguno`.

**Confirmar** con el botón `Agregar (N)` o `⌘Enter`; deshabilitado con N=0. Al cerrarse, el
diálogo resetea búsqueda y selección.

No se usa un componente `checkbox` de shadcn: no está instalado, y las filas clickeables con
un icono `Check` siguen el patrón que ya usa el dropdown de tasks del drawer.

## Flujo de datos

1. El usuario confirma → el diálogo llama `onAdd(taskNames, connectTo)`.
2. `workflow-editor.handleAddTasks` corre `applyAddedTasks`, y sobre el resultado corre
   `autoLayout` (dagre) sobre **todo** el grafo. Esto pisa las posiciones ajustadas a mano;
   fue una decisión explícita a favor de que el resultado quede prolijo. El `Auto-ordenar`
   del topbar ya hacía exactamente esto, así que el comportamiento no es nuevo.
3. `setNodes(resultado)` y `setSelectedNodeId(focusId)` → el drawer abre en el primer nodo
   nuevo, listo para cargarle los args.

## Recorrer los nodos

El drawer recibe `nodes` (para saber índice y total) y un `onNavigate(delta)`. Muestra
`‹ 3/20 ›` en el header; `‹`/`›` y `⌘↓`/`⌘↑` mueven la selección al nodo anterior/siguiente
en el orden del array `nodes`, sin cerrar el drawer.

`⌘↓`/`⌘↑` en lugar de `Tab` porque `Tab` navega los campos del form, y en lugar de
`Alt+flecha` porque en macOS eso mueve el cursor por palabras dentro de los inputs.

El listener va sobre el contenido del `Sheet`, no sobre `window`, para no capturar teclas
cuando el drawer está cerrado. Los extremos del rango no hacen wrap: en el nodo 1, `⌘↑` no
hace nada.

No se centra el nodo en el canvas al navegar. Es agradable pero no hace falta para el
objetivo, y pide meter la instancia de React Flow en el editor.

## Manejo de errores

No hay I/O nuevo, así que no hay errores nuevos que manejar. Los estados degradados que sí
importan:

- **`knownTaskNames` vacío** (sin workers conectados, o todavía cargando): la lista aparece
  vacía con el mensaje de que no hay tasks conocidas. El input de custom task sigue
  funcionando, así que el diálogo nunca queda inutilizable.
- **Nodos sin task asignada**: se pueden crear, pero el backend rechaza `taskName` vacío al
  guardar. Ya pasa hoy y el error se muestra en la barra del editor. No lo cambiamos acá.
- **Ciclos**: imposibles por construcción. Los nodos nuevos no tienen dependencias, y el
  target solo gana dependencias hacia nodos recién creados.

## Tests

En `lib/workflow-graph.test.ts`, que ya existe:

`applyAddedTasks`
- crea un nodo por taskName, con `label` vacío y el `taskName` puesto
- `kind: "node"` → el target queda con los N ids nuevos en `dependsOn`, preservando los que
  ya tenía
- `kind: "new"` → aparece un nodo extra con `taskName` vacío y `dependsOn` = los N ids;
  `focusId` es el primero de los nuevos, no el final
- `kind: "none"` → nadie gana dependencias
- no muta el array ni los objetos de entrada

El diálogo y el drawer no se testean: sin jsdom no hay forma de montar componentes.
