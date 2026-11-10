# C4 model of RagAssist

**Type:** Architecture · **Audience:** engineers, architects and reviewers who need to find their way in the system · **Verified against:** `a989287`

**In plain English:** This folder draws RagAssist at four zoom levels, like a map. First you see the whole system and the
people around it. Then you zoom into the containers, then into the parts of one container, then into the code. Extra pages
show how requests move over time and where the containers run. Start at page 1 and zoom in only as far as you need.

The C4 model is a method of [Simon Brown](https://c4model.com). It splits a software system into four levels:
**Context**, **Container**, **Component** and **Code**. This project adds two supporting views: **dynamic** views (what
happens over time) and a **deployment** view (where the containers run). The writing rules for these pages are in
[the writing style guide](../contributing/writing-style.md).

## The pages

| Page | C4 level | Question it answers | Mermaid type |
|---|---|---|---|
| [01 System context](01-system-context.md) | 1 Context | Who uses RagAssist and which outside systems does it call? | `C4Context` |
| [02 Containers](02-containers.md) | 2 Container | Which processes and data stores make up RagAssist, and how do they talk? | `C4Container` |
| [03 Components of the api](03-components-api.md) | 3 Component | What is inside the `api` container? | `C4Component` |
| [04 Components of the assistant graph](04-components-assistant-graph.md) | 3 Component | Which nodes, edges and ports make one assistant turn? | `flowchart`, `C4Component`, `stateDiagram-v2` |
| [05 Components of ingestion](05-components-ingestion.md) | 3 Component | How does an uploaded file become searchable passages? | `C4Component`, `flowchart`, `stateDiagram-v2` |
| [06 Components of the web app](06-components-web-app.md) | 3 Component | What is inside the browser application? | `C4Component`, `flowchart`, `stateDiagram-v2` |
| [07 Code level](07-code-level.md) | 4 Code | What are the key classes and functions? | `classDiagram` |
| [08 Dynamic views](08-dynamic-views.md) | Dynamic | What happens, step by step, in each main scenario? | `sequenceDiagram` |
| [09 Deployment](09-deployment.md) | Deployment | Which nodes run which containers? | `C4Deployment`, `flowchart` |

The Excalidraw files in [`docs/diagrams/`](../diagrams/README.md) give four free-form pictures of the same system.

## How to read a view

1. Read the title and the scope line under it. They say what the view shows and what it leaves out.
2. Read the sentence above the diagram. It says what to look for.
3. Read the diagram. Each box is one element. Each arrow is one relationship.
4. Read the table or list under the diagram ("In text"). It gives every relationship in words. A screen reader uses it, and
   so can you when the diagram does not draw.
5. Follow the links to ADRs, arc42 sections and reference pages for the reasons and the details.

Each diagram shows **one** zoom level. A diagram never mixes a person, a container and a class.

## Notation key

| Shape or line | Meaning |
|---|---|
| Person (a figure) | A human who uses the system, with their role in RagAssist |
| `System` box | The system that this document describes (RagAssist) |
| `System_Ext` box | A system that RagAssist does not own: a provider, a SaaS, a trace service |
| `Container` box | A deployable unit that runs on its own: a process, a web server or a database. It is not a Docker term only. |
| `ContainerDb` box | A container whose main job is to store data |
| `Component` box | A group of code inside one container, with one job |
| Dashed frame | A boundary: the system, a container or a deployment node |
| Arrow | One relationship. The label has a verb. The second label, when present, is the protocol. |
| `Deployment_Node` | A place where containers run: a host, a Docker network, a Docker container |

Notes about the notation:

- Boxes carry a name, a technology and a short description. Names match the code and the [glossary](../glossary.md).
- Arrows point from the caller to the callee, or from the sender to the receiver of the data.
- A dashed arrow in a flowchart means an optional or conditional path. The text says which.
- A box that says "optional" is off in the default configuration or needs a setting.

## Mermaid C4 is experimental

GitHub draws Mermaid diagrams, but the C4 diagram types in Mermaid are marked as experimental. Two things follow:

- The layout is automatic. The position of a box can differ from what you expect, and a long label can overlap a line.
- A viewer can fail to draw a C4 diagram. Every page therefore repeats its relationships in a table or list, and most pages add a
  plain `flowchart` as a fallback.

If a C4 diagram does not draw, read the "In text" section of the page. It has the same facts.

## Where the facts come from

Every name on these pages comes from the code at commit `a989287`, from a migration, from the compose file, or from an ADR.
Where a fact could not be checked, the page says `Unverified:`.

| Source | Pages that use it |
|---|---|
| `src/ragassist/main.py`, `runtime.py`, `container.py` | 02, 03, 09 |
| `src/ragassist/modules/assistant/` | 03, 04, 08 |
| `src/ragassist/modules/knowledge/`, `src/ragassist/worker/main.py` | 05, 08 |
| `frontend/src/` | 06, 07, 08 |
| `compose.yaml`, `infra/` | 02, 09 |
| [ADR 0008](../adr/0008-live-events-handoff-and-detached-turns.md), [ADR 0014](../adr/0014-web-delivery.md), [ADR 0015](../adr/0015-caching.md), [ADR 0016](../adr/0016-liquid-redesign.md) | 02, 06, 08, 09 |

## Related documentation

- [arc42 building block view](../arc42/05-building-block-view.md) and [runtime view](../arc42/06-runtime-view.md) explain the same
  structure in the arc42 layout.
- [arc42 deployment view](../arc42/07-deployment-view.md) holds the facts that page 09 draws.
- [Ports and adapters reference](../reference/ports-and-adapters.md) lists every port and adapter.
- [Assistant graph reference](../reference/assistant-graph.md) lists the graph state and the nodes.
- [Frontend structure reference](../reference/frontend-structure.md) lists the web app files.
- [Glossary](../glossary.md) defines the project terms.
