# Writing style for RagAssist documentation

**Type:** Reference · **Audience:** anyone who writes or reviews documentation · **Verified against:** `cc322bf`

**In plain English:** Write short sentences. Say one thing at a time. Use the same word for the same thing. Show a
diagram when a picture is faster than words. Never write a secret, a password or a real host name.

This page is the rule book for every file in `docs/`. It joins five methods. Each method has one job.

| Method | Its job here | Where you see it |
|---|---|---|
| **ASD-STE100** (Simplified Technical English) | Controls the words and the sentences | The body text of every page |
| **Plain English** | Controls the tone and the reader's first minute | The "In plain English" box at the top of each page |
| **Diátaxis** | Controls what kind of page it is | The four folders `tutorials/`, `how-to/`, `reference/`, `explanation/` |
| **arc42** | Controls the structure of the architecture description | `docs/arc42/` |
| **C4 model** | Controls the zoom level of the diagrams | `docs/c4/` |

> **Note.** This project writes *in the style of* ASD-STE100. It does not claim certification. The official
> specification is owned by ASD (AeroSpace and Defence Industries Association of Europe). Use it as a guide and not as a
> test that pages pass or fail.

## 1. Page header

Start every page with this block, in this order:

```markdown
# Title in sentence case

**Type:** Tutorial | How-to | Reference | Explanation | Architecture · **Audience:** who this is for · **Verified against:** `<short commit>`

**In plain English:** two or three short lines. What is this page? Why would I read it?
```

- **Verified against** is the commit that held the code when you checked the facts. Update it when you re-check.
- If you could not check a fact in the code, write `Unverified:` before it. Do not guess.

## 2. Words and sentences (ASD-STE100 in short)

1. **Write short sentences.** Procedures: 20 words or fewer. Descriptions: 25 words or fewer.
2. **One idea in each sentence.** Split a long sentence. Do not join ideas with a semicolon.
3. **Use the active voice.** Write "The API rejects the token", not "The token is rejected."
4. **Use the imperative for steps.** Write "Open the file." Do not write "You should open the file."
5. **Use the simple present tense.** Use the future only when time matters.
6. **Use one word for one meaning.** Keep the same word for the same thing in all pages (see the
   [glossary](../glossary.md)). Do not use a synonym for variety.
7. **Choose the simple word.** Write *use*, not *utilise*. Write *start*, not *commence*. Write *check*, not *ascertain*.
8. **Do not use idioms, jokes or phrasal verbs that have more than one meaning.** Write *remove*, not *take out*.
   Write *stop*, not *shut down*, unless the thing is a computer.
9. **Do not use contractions.** Write "do not", not "don't".
10. **Keep the articles.** Write "Open the file", not "Open file".
11. **Limit noun clusters to three nouns.** Write "the token for the refresh session", not "refresh session token
    handling configuration".
12. **Write numbers as digits.** Write units with a space: `15 minutes`, `50 MiB`.
13. **Keep paragraphs short.** Six sentences at most. Prefer a list or a table when the content is a list or a table.
14. **Define a term at its first use on a page.** Link to the glossary.
15. **Name the actor.** Say who does the action: the API, the worker, the admin, the browser.

### Procedures

- Number the steps. Put **one action** in each step.
- Put the result after the action: "Run the command. The command prints `ready`."
- Put a **WARNING** or **CAUTION** *before* the step that it covers. Never after.

```markdown
> **WARNING.** This command deletes all data in the local database. Do not run it on a shared system.
```

| Label | Meaning |
|---|---|
| **WARNING** | A person can lose data, a secret can leak, or tenant isolation can break |
| **CAUTION** | The system can stop working or give a wrong result |
| **NOTE** | Extra information that is useful but not required |

## 3. Plain English (the first minute)

- Open every page with the **In plain English** box. A new reader must understand the purpose after reading it.
- Speak to the reader as *you* in tutorials and how-to guides. Use the third person in reference and architecture.
- Prefer a concrete example to an abstract rule.
- Do not hide the answer. Put the conclusion first and the reason after it.

## 4. Diátaxis: what kind of page is this?

Each page has **one** type. Do not mix types in one page. Link to the other types.

| Type | Folder | The reader wants to… | Write it as… | Do not… |
|---|---|---|---|---|
| **Tutorial** | `docs/tutorials/` | learn by doing | A guided lesson with a safe result at the end | Explain theory or give options |
| **How-to** | `docs/how-to/` | finish a real task | Numbered steps for one goal, with checks | Teach basics or explain why |
| **Reference** | `docs/reference/` | look up a fact | Dry, complete, ordered tables and lists | Give opinions or steps |
| **Explanation** | `docs/explanation/` | understand why | Discussion, trade-offs, history, alternatives | Give step lists |

The architecture description is a fifth, fixed structure. It follows arc42 and C4 and lives in `docs/arc42/` and
`docs/c4/`. Treat it as **explanation with a standard layout**.

## 5. arc42 and C4

- `docs/arc42/` holds the twelve arc42 sections, numbered `01` to `12`. Do not rename or renumber them.
- `docs/c4/` holds the C4 views at four zoom levels: **Context**, **Container**, **Component** and **Code**. It also
  holds the *dynamic* views (sequence diagrams) and the *deployment* view.
- Each C4 diagram shows **one** zoom level. Do not mix a person, a container and a class on one diagram.
- Each diagram has a title, a one-line scope and a key to its shapes. Each arrow has a verb and, where useful, the
  protocol.
- A decision with a reason belongs in an ADR in `docs/adr/`. Link to it. Do not repeat it.

## 6. Diagrams

| Use… | When… |
|---|---|
| Mermaid `flowchart` | A process, a decision or a data flow |
| Mermaid `sequenceDiagram` | Messages between parts over time |
| Mermaid `C4Context`, `C4Container`, `C4Component` | The C4 views |
| Mermaid `erDiagram` | The database tables |
| Mermaid `stateDiagram-v2` | A life cycle (a job, an escalation, a session) |
| Excalidraw file in `docs/diagrams/` | A free-form overview that needs hand layout |

Rules:

1. Put the diagram in a fenced block with the language `mermaid`. GitHub draws it.
2. Add a sentence **above** the diagram that says what the reader must see in it.
3. Keep a diagram to about 15 nodes. Split it when it grows.
4. Do not put the only copy of a fact in a diagram. Say the same fact in text as well, for readers who use a screen
   reader.
5. Name nodes with the same words as the [glossary](../glossary.md) and the code.
6. An Excalidraw source file (`*.excalidraw`) must have a matching SVG or a Mermaid copy, or a text description next to
   it. Open the `.excalidraw` file at <https://excalidraw.com> or in the editor extension.

## 7. Safety rules for the content (hard rules)

These rules come from `AGENTS.md`. A page that breaks them is rejected.

1. **No secrets.** Never write a password, key, token or connection string with a credential. Not even as an example.
   Write the *name* of the setting (for example `JWT_ALGORITHM`) and say where its value lives (`.env`).
2. **No deployment values.** Never write a real host, port, role name or endpoint as a fact about the deployment. Use the
   setting name or a placeholder in angle brackets, for example `<WEB_PORT>`. A port that is part of a public standard
   (for example 443 for HTTPS) is allowed.
3. **No key-shaped text.** Do not write text that looks like a provider key, even a fake one. The secret scanner
   (`scripts/check_secrets.py`) scans `docs/` and blocks the commit.
4. **No AI attribution.** Do not write that a model or an assistant wrote a page.
5. **Do not copy tenant data.** Use invented names: `Acme`, `ada@example.test`, a workspace slug such as `demo`.
6. **Say what you did not check.** Use `Unverified:`. A true gap is better than a confident error.

## 8. File and link rules

- File names use lower-case words joined by hyphens: `configure-llm-providers.md`.
- Use **relative** links: `[glossary](../glossary.md)`. Never use `file:///` or absolute disk paths.
- Link to code with a repository path in backticks, for example `src/ragassist/shared/db/uow.py`. Add a line number only
  if the line is stable.
- Every page is reachable from `docs/README.md`.

## 9. Review checklist

- [ ] The header block is complete and the commit is current.
- [ ] The page has **one** Diátaxis type.
- [ ] Sentences are short and active. Steps have one action each.
- [ ] Each term matches the glossary.
- [ ] Each diagram has a lead-in sentence, a title and a text equivalent.
- [ ] Each fact came from the code, a test, a config file or an ADR. Gaps are marked `Unverified:`.
- [ ] No secret, no deployment value, no key-shaped text.
- [ ] All links resolve.
