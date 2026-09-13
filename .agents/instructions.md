# .agents/ — what this is and how to keep it alive

This directory holds a knowledge base about the **esquared-academy-lms**
codebase itself, written for an AI assistant (Claude) to read at the start
of a session instead of re-reading every file from scratch. It is not
documentation for end users of the LMS, and it is not the in-app "knowledge
graph" / "knowledge map" feature that already exists in the product
(`templates/admin/knowledge_graph.html`, the topic-tree API, the student
knowledge-map panel) — that's a completely different thing that happens to
share the name. Don't merge the two.

Two files:

- **knowledge_graph.md** — dense, agent-facing. Not written for easy human
  reading; written so a future Claude session can load one file and know
  the schema, the security model, the URL surface, the business logic, and
  the gotchas without opening 15,000 lines of source. It trades prose
  polish for information density.
- **instructions.md** (this file) — for you, Uzair, and for Claude: how the
  system works and the rule for keeping it honest.

## The rule

**Whenever code in this repo changes in a way that affects something
knowledge_graph.md describes, update knowledge_graph.md in the same
session — before finishing up, not "later."** A knowledge base that drifts
from the code is worse than no knowledge base, because it gets trusted
without being checked.

This is a standing instruction to Claude, not something Uzair needs to ask
for each time. If Claude edits models.py, admin.py, access.py, urls.py, or
adds/removes a management command — or does anything else this file
describes — it should open `.agents/knowledge_graph.md`, find the relevant
section, and fix it before considering the task done.

## What counts as "affects the knowledge graph"

Concretely, update the graph when you:

- Add, remove, or rename a model, field, or relationship -> section 4 (data
  model), and consider whether the ERD (`academy-lms-erd.drawio` +
  `claude/lms-schema-erd.md` in the claude.ai Project) needs regenerating
  too -- see that doc's own "How it was built" section for the ast-based
  regeneration approach.
- Add or change a role, a permission rule, or anything in
  `access.scope_queryset` / `_scope_to_students` -> section 5.1. This is the
  security-sensitive section; be precise, and re-run
  `app/check_row_scoping.py` (not just `manage.py test`) after any such
  change, and note the result.
- Add/change a Submission or Handout state or transition method -> section 5.5.
- Change the grading algorithm or its weight-resolution rules -> section 5.6.
- Add a new API resource, endpoint, or `@action` -> section 7.
- Add a new admin_views.py page or change routing in lms/urls.py -> section 7/9.
- Add/remove a management command -> section 10.
- Add a new versioned-immutable entity, a new append-only entity, or
  anything following (or deliberately breaking) the patterns listed in
  section 12 -> update section 12, and say explicitly if you're introducing
  an exception.
- Change settings that affect deployment or infra (DB engine, middleware
  order, auth backend, media storage) -> section 3.
- Anything that makes an existing "gotcha" in section 12 no longer true
  (e.g. HoD row-scoping gets a real department table) -> remove or update
  that bullet rather than leaving stale warnings in place.

Small/local changes that don't need a graph update: bug fixes that don't
change behavior described here, template/CSS tweaks, test additions that
don't change what's tested, docstring wording changes, dependency bumps
that don't change architecture.

## How to update it well

- Keep the density. This file is not meant to be skimmed by a human in a
  meeting; it's meant to be loaded whole by an LLM. Prefer a precise
  sentence over a heading-and-bullet-list treatment if it's shorter and as
  clear. Tables are fine for enumerable things (commands, roles).
- Update the frontmatter: bump `generated` (date) and `covers_commit` (the
  commit you're leaving the repo at) whenever you touch the file.
- Don't just append. If a fact changes, edit the existing sentence describing
  it -- this file should never contain two contradictory statements about
  the same behavior.
- If you're not sure whether something is still true, verify it against the
  actual source (grep/read the file) rather than trusting your memory of an
  earlier session -- the whole point of this file is to save that work
  *when it's still accurate*, not to save it once and stop checking.
- If you regenerate the graph from scratch (e.g. asked to "redo the
  knowledge graph"), the fastest reliable method -- used to build this
  version -- is: for each Python module, run an AST-based structural
  extractor (classes, bases, methods with first-line docstrings, module-
  level functions, imports) rather than reading raw source for the large
  files (models.py, admin.py, admin_views.py, views.py are each 1,000-
  3,400 lines); then read the smaller, logic-dense modules
  (access.py, grading.py, files.py, audit.py, middleware.py, columns.py,
  dashboard.py) in full, since they're short and every line matters. A
  short Python script doing this (ast.parse + ast.iter_child_nodes) is
  quick to rewrite if needed; don't hand-transcribe 3,000-line files.

## What NOT to put in knowledge_graph.md

- Secrets, `.env` contents, real student/staff PII, or anything from the
  `docs/` folder's spreadsheets (login lists, setup workbooks) -- those are
  data, not architecture.
- Anything that duplicates the ERD's field-by-field detail. Point to the
  ERD doc instead of re-listing every field of every model -- the graph's
  section 4 already summarizes relationships and behavior that the ERD,
  being a static diagram, can't show; keep it that way rather than letting
  the two documents diverge on field lists.
- Speculative "should probably" notes about future work -- this file
  describes what the code *does*, not a roadmap. Roadmap items belong in
  an issue tracker or a separate doc if Uzair wants one.

## Where things live, for reference

- This repo, on Uzair's Mac: `~/workspace/esquared-academy-lms`
  (the code Claude actually read to build this).
- The claude.ai Project attached to LMS work is "Esquared Academy LMS",
  containing `claude/lms-schema-erd.md` (the ERD write-up) -- that's a
  different storage location from this repo's own `.agents/` folder and
  from the repo's `academy-lms-erd.drawio` file. All three should stay
  consistent; this file and the ERD doc are the two places that need
  manual updates (the .drawio is generated from models.py).
