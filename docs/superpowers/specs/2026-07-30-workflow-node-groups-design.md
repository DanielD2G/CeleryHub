# Grupos de nodos en workflows

**Fecha:** 2026-07-30
**Estado:** diseño aprobado
**Servicio:** `services/celery-gateway` (backend) + `packages/web` (frontend)

## Problema

Un fan-in real —20 tasks distintas que corren antes de una final— produce 20 nodos sueltos en
el canvas. Eso trae dos molestias: el canvas se vuelve ilegible, y no hay forma de tratar a
las 20 como una unidad (conectarlas de a una, setearles la queue de a una).

La salida tentadora es volver al modelo viejo de "un nodo con varias tasks". No sirve: ese
modelo obligaba a las tasks de un step a compartir `args`/`kwargs`/`queue`, y el caso real
necesita args propios por task. Fue justamente la razón #1 por la que se migró a 1 nodo = 1
task en [2026-06-19](./2026-06-19-workflow-one-task-per-node-design.md).

## Objetivo

Un **grupo** que agrupa nodos, se colapsa en el canvas, y funciona como origen y destino de
dependencias — sin tocar el engine y sin que los nodos pierdan su config individual.

## Principio rector

El grupo es un concepto de **autoría y presentación**. Se expande a `dependsOn` concretos al
guardar, y el engine nunca se entera de que existe.

Esto se apoya en un hecho ya verificado: `_advance_workflow` espera a que *todas* las
dependencias de un nodo estén terminales y recién ahí evalúa su `condition` sobre ellas
(`workflow_engine.py:203`). O sea que "esperar a que todas las tareas del grupo estén" **ya
es expresable hoy**: es un nodo con los 20 ids en `dependsOn` y `condition: all_succeeded`.
El grupo no agrega semántica de ejecución; agrega una forma cómoda de escribir eso.

Corolario importante: no se introduce una segunda noción de join. Sigue habiendo una sola
—`condition` sobre `dependsOn`— que fue el smell que hundió al modelo de steps.

## Modelo de datos

Migración Alembic `0006`. Aditiva: no rompe workflows existentes.

### `WorkflowGroup` (nueva)

```
id           str  PK
workflow_id  str  FK workflows.id ON DELETE CASCADE
label        str
collapsed    bool          -- estado de colapso en el canvas
depends_on   str           -- JSON list de node ids: el grupo como ORIGEN
position_x   float | None
position_y   float | None

índice: (workflow_id)
```

No lleva queue, timeout ni condition: la config compartida es un bulk-edit (ver más abajo),
no herencia, así que no hay nada que persistir.

### `WorkflowNode` (dos columnas nuevas)

```
group_id           str | None   -- a qué grupo pertenece; NULL = suelto
depends_on_groups  str          -- JSON list de group ids: el grupo como DESTINO, default "[]"
```

`depends_on` no cambia de forma ni de significado, y sigue siendo **lo único que el engine
lee**.

## Expansión al guardar

`update_workflow` ya hace full-replace de todos los nodos (`routers/workflows.py`, el
`delete(WorkflowNode)` seguido de recrear). Sobre eso se apoya todo: cada guardado reescribe
el grafo entero, así que expandir en ese punto deja la base siempre consistente.

En el router, antes de validar:

```
depends_on(n) = depends_on(n)
              ∪ ⋃ { miembros(g) : g ∈ depends_on_groups(n) }
              ∪ depends_on(grupo(n))        si n pertenece a un grupo
```

Se persisten **las dos cosas**:

- el `depends_on` expandido → lo que ejecuta el engine
- la intención (`depends_on_groups` del nodo, `depends_on` del grupo) → sin esto, en el
  guardado siguiente sería imposible distinguir "depende del grupo" de "depende de estos 20
  nodos puntuales", y agregar un miembro no se propagaría

`_validate_dag` corre **después** de expandir, sobre un grafo concreto. Eso hace que los
ciclos que pasan por un grupo (el grupo A depende de X, y X está dentro de A) los cace Kahn
sin una línea de lógica nueva.

### Por qué al guardar y no al arrancar el run

La alternativa era que `depends_on` aceptara referencias `group:<id>` y que el engine las
resolviera al crear los `NodeRun`. Se descartó: obliga a `_validate_dag` a detectar ciclos
sobre un grafo mixto nodo/grupo, con casos borde propios, y mete grupos en la parte del
sistema que ejecuta trabajo real. Como toda edición pasa por un guardado full-replace, no
existe ningún escenario en que resolver al arrancar esté más al día que resolver al guardar.

**El engine no se toca.** `_advance_workflow`, `_evaluate_condition`, `_dispatch_node` y el
manejo de timeouts quedan exactamente como están.

## API

- `GroupInput` / `GroupResponse`: `id`, `label`, `collapsed`, `dependsOn`, `positionX/Y`.
- `WorkflowResponse.groups`: lista de grupos junto a `nodes`.
- `NodeInput` / `NodeResponse` ganan `groupId` y `dependsOnGroups`.
- Create y update aceptan `groups` y hacen full-replace también de los grupos, igual que con
  los nodos.
- Import/export incluyen `groups`. Un JSON sin `groups` se importa como workflow sin grupos,
  así que los exports viejos siguen entrando.

## Canvas

React Flow v12 tiene nodos-grupo nativos (`parentId` + `extent: "parent"`), así que el estado
**expandido** es casi gratis: los miembros se dibujan dentro de la caja y se arrastran con
ella.

El estado **colapsado** es el grueso del trabajo del frontend:

- los nodos miembro no se renderizan; queda un solo nodo `Scrapers (20)`
- los edges de los miembros se **agregan** sobre la caja: 20 aristas hacia el nodo final se
  dibujan como una. Un edge agregado se marca visualmente distinto de uno común, para que se
  entienda que representa N dependencias
- conectar contra la caja escribe la intención según la dirección: hacia la caja →
  `group.dependsOn`; desde la caja hacia un nodo → `dependsOnGroups` de ese nodo

Operaciones de grupo en el editor: crear grupo a partir de la selección, renombrar, sacar un
nodo del grupo, disolver el grupo.

## Config compartida

Un panel del grupo con queue, timeout y condition, y un botón **"Aplicar a los N"**. Escribe
el valor dentro de cada nodo miembro y termina ahí. Cada nodo sigue siendo dueño de su config
y la muestra en su drawer.

**Los args y kwargs nunca se comparten**, ni siquiera como bulk-edit: son lo que distingue a
un miembro de otro.

### Asimetría deliberada

Las **dependencias** del grupo se mantienen sincronizadas: agregás el miembro 21 y el nodo
final pasa a esperarlo solo. La **config** no: el miembro 21 nace con los defaults, no con la
queue que aplicaste antes.

Es intencional. Las dependencias son estructura del DAG y desincronizarlas produce workflows
que corren mal; la config son valores, y la herencia en vivo traía ambigüedad (`NULL` pasa a
significar dos cosas) y hacía que el drawer del nodo ya no te dijera qué va a correr. Pero es
una regla que hay que conocer, y la UI debe hacerla evidente: al agregar miembros a un grupo
con config aplicada, ofrecer aplicarla a los nuevos.

## Casos borde

- **Nodo que pertenece a G y además tiene G en `dependsOnGroups`**: rechazo explícito al
  validar, con mensaje propio ("un nodo no puede depender del grupo que lo contiene"). Se
  prefiere el error a auto-excluirse en silencio: el silencio produce un workflow que corre
  distinto de como se lee.
- **Borrar un grupo**: los miembros quedan sueltos, no se borran. Las referencias a ese grupo
  en `dependsOnGroups` de otros nodos se limpian en el mismo guardado.
- **Grupo vacío**: permitido. Expande a nada, y un nodo que dependa de él queda sin esa
  dependencia.
- **Grupo con un solo miembro**: permitido, sin tratamiento especial.
- **Miembro con dependencias propias fuera del grupo**: permitido. Se unen a las que hereda
  del grupo.

## Supuestos

- `collapsed` se persiste en la base, no por usuario: es parte de cómo se lee el workflow, no
  una preferencia personal.
- Un nodo pertenece a lo sumo a un grupo.

## Tests

**Backend**
- expansión: destino, origen, ambos a la vez, grupo vacío, grupo borrado, miembro con deps
  propias
- validación: ciclo que pasa por un grupo, nodo que depende de su propio grupo
- router: create/update round-trip preservando la intención (`dependsOnGroups` y
  `group.dependsOn` sobreviven al full-replace)
- engine: un test de regresión que confirme que un workflow con grupos produce exactamente
  los mismos `NodeRun` que el equivalente con `dependsOn` escritos a mano

**Frontend**
- helpers puros en `lib/workflow-graph.ts`: armado de nodos-grupo para React Flow, y
  agregación de edges al colapsar (N aristas de miembros → 1 arista de grupo)
- el canvas y los diálogos no se testean: el proyecto no tiene jsdom

## Fuera de alcance (YAGNI)

- Grupos anidados
- Un nodo en varios grupos
- Args o kwargs a nivel grupo
- Correr un grupo suelto, fuera de su workflow
- Herencia de config en vivo
