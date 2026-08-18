# Workflows como secuencia de pasos

**Fecha:** 2026-07-30
**Estado:** diseño propuesto — pendiente de aprobación
**Servicio:** `services/celery-gateway` (backend) + `packages/web` (frontend)
**Reemplaza a:** [grupos de nodos](./2026-07-30-workflow-node-groups-design.md) y absorbe
parte de [bulk add tasks](./2026-07-30-bulk-add-tasks-design.md)

## Cambio de enfoque

Editar un DAG a mano resultó caro en todas las dimensiones: arrastrar 20 edges, decidir
posiciones, detectar ciclos, colapsar cajas, agregar aristas. Cada feature que agregábamos
para hacerlo llevadero (bulk-add con auto-wiring, grupos con expansión) era complejidad para
sostener un modelo de autoría que el usuario no necesita.

**El usuario no está armando un grafo arbitrario. Está armando una secuencia.**

Así que el modelo de autoría pasa a ser una lista ordenada, y el grafo se **genera**.

```
1  scrape_fravega
2  ▾ Scrapers (20)      ← un paso con 20 tasks en paralelo
3  consolidar           ← espera a las 20
```

Cada task sigue siendo un nodo individual con sus propios args, kwargs, queue y timeout. Eso
es lo que distingue esto del modelo de steps que se eliminó en junio: **el grupo es un
contenedor de presentación y orden, no una unidad de ejecución con config compartida.**

## Modelo conceptual

- Un workflow es una **secuencia de pasos** numerados `0..N`.
- Un paso contiene **una o más tasks**. Con una sola es una task suelta; con varias es un
  grupo, y corren en paralelo.
- El paso `i` arranca cuando **todas** las tasks del paso `i-1` están terminales y se cumple
  la `condition`.
- El `dependsOn` de cada task se genera: todas las tasks del paso anterior.

Los ciclos son imposibles por construcción. `_validate_dag` sigue existiendo como red de
seguridad, pero deja de poder fallar por input del usuario.

## Qué se pierde

DAGs arbitrarios. Ya no se puede expresar que la task D dependa solo de A cuando B y C están
en el mismo paso, ni un diamante, ni saltear un paso. Todo lo que no sea "capas secuenciales"
deja de ser representable.

Es la contrapartida deliberada de la simplicidad. Vale la pena decirlo fuerte porque es
irreversible desde la UI: si más adelante hace falta un DAG real, hay que volver a construir
el editor de grafo.

Lo que **no** se pierde: el paralelismo (es el grupo), las condiciones de join (siguen en la
task), y la config individual por task.

## Modelo de datos

Migración Alembic `0006`. Aditiva.

`WorkflowNode` gana dos columnas:

```
stage        int          -- índice del paso, 0-based, NOT NULL default 0
stage_label  str | None   -- nombre del grupo; sólo tiene sentido con varias tasks en el paso
```

`depends_on` **se queda**, con el mismo significado, y sigue siendo lo único que el engine
lee. Pasa a ser un campo derivado: lo escribe el backend, no el usuario.

`position_x` / `position_y` quedan sin uso: el layout siempre se calcula. No se dropean en
esta migración para no mezclar cosas; se limpian aparte.

No hace falta tabla de grupos. Un grupo es "las tasks que comparten `stage`", y su nombre es
`stage_label`. Eso es lo que quiere decir que el grupo es un embebido: no es una entidad, es
una propiedad compartida.

## Generación del DAG al guardar

`update_workflow` ya hace full-replace de todos los nodos, así que la generación va ahí:

```
depends_on(n) = [ id de cada nodo m tal que stage(m) == stage(n) - 1 ]
```

Los nodos del paso 0 quedan con `depends_on` vacío y arrancan de una.

**El engine no se toca.** `_advance_workflow`, `_evaluate_condition`, `_dispatch_node` y los
timeouts quedan exactamente como están: siguen viendo ids concretos.

Se persiste el `depends_on` generado además del `stage`. El `stage` es la intención y lo que
la UI edita; el `depends_on` es el resultado que ejecuta el engine.

### Condition

`condition` se queda **en la task**, como hoy. Todas las tasks de un paso comparten el mismo
valor en la práctica, y la UI lo edita a nivel paso aplicándolo a las tasks del paso. No se
crea un campo de condition por paso: sería una segunda fuente de verdad para lo mismo.

## Migración de workflows existentes

Se deriva `stage` = **nivel topológico** de cada nodo (longitud del camino más largo desde una
raíz). Para un DAG que ya es por capas, el resultado es idéntico. Para uno que no lo es, un
nodo puede terminar esperando más de lo que esperaba antes.

El error va siempre en la dirección segura: se espera de más, nunca de menos, así que ningún
workflow migrado va a despachar una task antes de tiempo. Aun así **cambia el comportamiento**
de los DAGs no-layered, y hay que avisarlo en el release.

Alternativa si preferís no arriesgar: corte limpio, como en las dos migraciones anteriores.
Es una decisión tuya, la dejo marcada abajo.

## UI: el editor pasa a ser una lista

El canvas deja de ser la superficie de edición. El editor es una lista vertical de pasos:

```
1   scrape_fravega                     ⋮
2 ▾ Scrapers (20)                      ⋮
      scrape_garbarino                 ⋮
      scrape_musimundo                 ⋮
      …
3   consolidar                         ⋮
```

- **Reordenar** pasos arrastrando. Es la única forma de cambiar el grafo.
- **`+ Tarea`** agrega un paso al final con una task.
- **`+ Grupo`** agrega un paso vacío al que se le suman tasks.
- **Colapsar/expandir** un grupo es local a la lista, no se persiste. Es una lista, no un
  diagrama: no hace falta guardar cómo se ve.
- **Sacar una task de un grupo** la convierte en su propio paso, insertado ahí.
- Click en una task abre el drawer de config que ya existe, sin cambios.

El **diálogo de selección múltiple** del spec de bulk-add se conserva tal cual, pero
simplificado: agrega N tasks a un paso. Desaparece el selector "Conectar a" —el cableado ya no
existe— y con él la mitad de su complejidad.

El **pager `‹ i/20 ›`** del drawer también se conserva: sigue siendo la forma de cargarle args
a 20 tasks seguidas sin cerrar nada.

### El canvas

Pasa a ser **solo lectura**: se genera con `autoLayout` (dagre, ya funciona) a partir de la
lista, para ver el workflow y para seguir las corridas. Se elimina del editor el arrastre de
edges, la inserción sobre una arista, el arrastre de nodos y el guardado de posiciones.

Esto borra buena parte de `workflow-canvas.tsx`, incluido el bug de arrastre que estamos
arrastrando, y hace irrelevante `wouldCreateCycle`.

## API

- `NodeInput` / `NodeResponse` ganan `stage` y `stageLabel`.
- `NodeInput` **deja de aceptar** `dependsOn`: es derivado. Un payload que lo mande se rechaza
  con un mensaje claro, en vez de ignorarlo en silencio.
- `NodeResponse` sí lo devuelve, para que el canvas de sólo lectura lo dibuje.
- Import/export pasan a `stage`/`stageLabel`. Un JSON viejo con `dependsOn` se puede importar
  derivando el stage por nivel topológico, igual que la migración.

## Tests

**Backend**
- generación: un paso, varios pasos, paso con N tasks, paso 0 sin deps
- derivación de stage por nivel topológico: DAG por capas (idéntico), DAG no-layered (espera
  de más), nodo suelto sin deps
- router: rechaza `dependsOn` en el input; round-trip preservando `stage` y `stageLabel`
- engine: test de regresión — un workflow por pasos produce los mismos `NodeRun` que el
  equivalente con `dependsOn` escritos a mano

**Frontend**
- helpers puros en `lib/workflow-graph.ts`: agrupar nodos por stage para la lista, reordenar
  pasos, sacar una task de un grupo, y generar los flow nodes/edges para el canvas de lectura
- la lista y los diálogos no se testean: el proyecto no tiene jsdom

## Supuestos que hay que confirmar

1. **El canvas queda de sólo lectura.** Si querés seguir pudiendo mover nodos a mano, cambia
   el alcance.
2. **Los workflows existentes se migran derivando el stage**, no se borran. La alternativa es
   corte limpio.

## Fuera de alcance (YAGNI)

- DAGs arbitrarios desde la UI
- Pasos anidados (un grupo dentro de un grupo)
- Condition por paso como campo propio
- Config compartida a nivel grupo
- Limpieza de `position_x` / `position_y`
