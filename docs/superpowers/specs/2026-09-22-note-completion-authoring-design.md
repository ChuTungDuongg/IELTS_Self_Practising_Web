# Note Completion Authoring Design

## Outcome

Replace Note Completion's legacy standalone `layout.nodes` authoring flow with a dedicated note document model. Authors edit semantic note blocks inline, type `{{gap}}` or use **Insert gap** to create linked questions at the caret, and see the same title, headings, bullets, indentation, and inline gaps in Builder Preview, Candidate, and Review.

## Scope and constraints

- Change only `note_completion`; Form, Flow-chart, Summary, Sentence, Text, Table, and Diagram behavior stays on its existing implementation.
- Keep PostgreSQL authoritative and all validation/evaluation in FastAPI.
- Reuse the existing TEXT question config, answer-key schema, and evaluator.
- Do not add a rich-text dependency or store `{{gap}}` in persisted content.
- Preserve UUID-bound questions, answer keys, and configs when text, style, indentation, block order, or gap placement changes.
- Preserve global Reading/Listening numbering by accepting the Builder-provided base question number.

## Data model

`config.layout` for Note Completion becomes:

```json
{
  "kind": "NOTE",
  "title": "HIRING A PUBLIC ROOM",
  "blocks": [
    {
      "id": "<uuid>",
      "style": "BULLET",
      "indent": 0,
      "segments": [
        { "id": "<uuid>", "type": "TEXT", "text": "the " },
        { "id": "<uuid>", "type": "GAP", "question_id": "<uuid>" },
        { "id": "<uuid>", "type": "TEXT", "text": " Room – seats 100" }
      ]
    }
  ],
  "columns": [],
  "rows": [],
  "nodes": []
}
```

The empty legacy collections keep `StructuredLayout` serialization compatible while `blocks` is the authoritative Note representation. Block styles are `HEADING`, `TEXT`, `BULLET`, and `EXAMPLE`; the optional note title is stored separately in `layout.title`. Indent is an integer from 0 through 3. Segment, block, gap, and question identities are UUIDs.

Persisted Note layouts require at least one non-empty block. Every GAP references one group question, every question is referenced exactly once, and all linked questions use valid TEXT answer keys. The initial unsaved Builder draft may contain one blank TEXT block and zero questions; it becomes saveable only after valid content and at least one gap exist.

## Authoring behavior

The editor owns one `contentEditable` text span per TEXT segment and one React button per GAP segment. When the active span contains one or more complete `{{gap}}` tokens, only that span is split left-to-right. Each token creates a new question and GAP UUID with `max_words: 2`, `max_numbers: 1`, and `{kind: "TEXT", accepted: ["answer"], case_sensitive: false}`. Existing segments and questions are untouched.

The Insert gap action performs the same split at the remembered caret. Enter creates a block below: BULLET continues BULLET, HEADING continues as BULLET, TEXT continues TEXT, and EXAMPLE continues TEXT. Block style and indent controls alter presentation only. Moving blocks or gaps reorders existing objects, then canonical numbering is derived from block order followed by segment order.

Dragging a gap removes the same segment object from its source block and inserts it into the target TEXT segment at the pointer caret. It never creates a replacement question. Removing a gap merges adjacent text and removes only its linked question. Removing a block without gaps is immediate; removing a block with gaps uses the shared confirmation dialog and lists the affected question numbers.

## Rendering

A dedicated Note renderer displays a centered non-empty title, bold HEADING blocks, automatic bullet markers for BULLET blocks, distinct EXAMPLE text, and consistent semantic indentation. Each GAP renders the existing question target attributes, question number, and compact input inline between surrounding text. Candidate, Preview, and Review use this same renderer.

## Legacy normalization

FastAPI normalizes legacy NOTE `nodes` before schema validation. Each legacy node becomes one block without guessing adjacency: TEXT becomes a TEXT-style block containing one TEXT segment; GAP becomes a TEXT-style block containing one GAP segment. UUIDv5 identities derived from group/node position make repeated normalization stable. Modern blocks are normalized without changing valid UUIDs. The normalized output clears `nodes` and uses `blocks`.

## Validation and testing

Frontend integrity checks and both backend reference-validation paths compare the ordered Note GAP list with the group question set, rejecting duplicates, unknown references, and orphans. Backend Pydantic models enforce UUID, style, indent, segment shape, non-empty persisted blocks, and title limits. Tests cover the model, shortcut/paste conversion, caret insertion, stable identity, gap drag, ordering, styles/indent, destructive actions, legacy normalization, inline candidate responses, Builder controls, and the existing Text/Table/other structured suites.
