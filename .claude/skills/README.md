# Skills

The single home for this repo's agent skills. Claude Code discovers skills only
under `.claude/skills/`, and web sessions run from a fresh clone, so the files
have to live here and be committed — there is no second copy anywhere in the
repo.

Distribution reuses these same files: `pyproject.toml` force-includes this
directory into the wheel as `pycreditools/_skills_utils/skills/mattpocock/`, so
`pasche-utils install-skills mattpocock` can drop them into another repo.
Re-generate this index after adding or removing a skill.

## Model-invocable (14)

Claude may trigger these on its own when the description matches.

- **[code-review](./code-review/SKILL.md)** — Review the changes since a fixed point (commit, branch, tag, or merge-base) along two axes — Standards (does the code follow this repo's documented coding standards?) and Spec (does the code match what the originating issue/PRD asked for?). Runs both reviews in parallel sub-agents and reports them side by side. Use when the user wants to review a branch, a PR, work-in-progress changes, or asks to "review since X".
- **[codebase-design](./codebase-design/SKILL.md)** — Shared vocabulary for designing deep modules. Use when the user wants to design or improve a module's interface, find deepening opportunities, decide where a seam goes, make code more testable or AI-navigable, or when another skill needs the deep-module vocabulary.
- **[diagnosing-bugs](./diagnosing-bugs/SKILL.md)** — Diagnosis loop for hard bugs and performance regressions. Use when the user says "diagnose"/"debug this", or reports something broken/throwing/failing/slow.
- **[domain-modeling](./domain-modeling/SKILL.md)** — Build and sharpen a project's domain model. Use when the user wants to pin down domain terminology or a ubiquitous language, record an architectural decision, or when another skill needs to maintain the domain model.
- **[git-guardrails-claude-code](./git-guardrails-claude-code/SKILL.md)** — Set up Claude Code hooks to block dangerous git commands (push, reset --hard, clean, branch -D, etc.) before they execute. Use when user wants to prevent destructive git operations, add git safety hooks, or block git push/reset in Claude Code.
- **[grilling](./grilling/SKILL.md)** — Grill the user relentlessly about a plan, decision, or idea. Use when the user wants to stress-test their thinking, or uses any 'grill' trigger phrases.
- **[migrate-to-shoehorn](./migrate-to-shoehorn/SKILL.md)** — Migrate test files from `as` type assertions to @total-typescript/shoehorn. Use when user mentions shoehorn, wants to replace `as` in tests, or needs partial test data.
- **[obsidian-vault](./obsidian-vault/SKILL.md)** — Search, create, and manage notes in the Obsidian vault with wikilinks and index notes. Use when user wants to find, create, or organize notes in Obsidian.
- **[prototype](./prototype/SKILL.md)** — Build a throwaway prototype to answer a design question. Use when the user wants to sanity-check whether a state model or logic feels right, or explore what a UI should look like.
- **[research](./research/SKILL.md)** — Investigate a question against high-trust primary sources and capture the findings as a Markdown file in the repo. Use when the user wants a topic researched, docs or API facts gathered, or reading legwork delegated to a background agent.
- **[resolving-merge-conflicts](./resolving-merge-conflicts/SKILL.md)** — "Use when you need to resolve an in-progress git merge/rebase conflict."
- **[scaffold-exercises](./scaffold-exercises/SKILL.md)** — Create exercise directory structures with sections, problems, solutions, and explainers that pass linting. Use when user wants to scaffold exercises, create exercise stubs, or set up a new course section.
- **[setup-pre-commit](./setup-pre-commit/SKILL.md)** — Set up Husky pre-commit hooks with lint-staged (Prettier), type checking, and tests in the current repo. Use when user wants to add pre-commit hooks, set up Husky, configure lint-staged, or add commit-time formatting/typechecking/testing.
- **[tdd](./tdd/SKILL.md)** — Test-driven development. Use when the user wants to build features or fix bugs test-first, mentions "red-green-refactor", or wants integration tests.

## User-invoked (19)

Reachable only when you type them — `disable-model-invocation: true`.

- **[ask-matt](./ask-matt/SKILL.md)** — Ask which skill or flow fits your situation. A router over the skills in this repo.
- **[decision-mapping](./decision-mapping/SKILL.md)** — Turn a loose idea into a sequenced map of investigation tickets, then drive them to resolution one at a time.
- **[edit-article](./edit-article/SKILL.md)** — Edit and improve articles by restructuring sections, improving clarity, and tightening prose. Use when user wants to edit, revise, or improve an article draft.
- **[grill-me](./grill-me/SKILL.md)** — A relentless interview to sharpen a plan or design.
- **[grill-with-docs](./grill-with-docs/SKILL.md)** — A relentless interview to sharpen a plan or design, which also creates docs (ADR's and glossary) as we go.
- **[handoff](./handoff/SKILL.md)** — Compact the current conversation into a handoff document for another agent to pick up.
- **[implement](./implement/SKILL.md)** — "Implement a piece of work based on a spec or set of tickets."
- **[improve-codebase-architecture](./improve-codebase-architecture/SKILL.md)** — Scan a codebase for deepening opportunities, present them as a visual HTML report, then grill through whichever one you pick.
- **[loop-me](./loop-me/SKILL.md)** — Grill me about specs for the workflows I want to build, within this workspace.
- **[setup-matt-pocock-skills](./setup-matt-pocock-skills/SKILL.md)** — Configure this repo for the engineering skills — set up its issue tracker, triage label vocabulary, and domain doc layout. Run once before first use of the other engineering skills.
- **[teach](./teach/SKILL.md)** — Teach the user a new skill or concept, within this workspace.
- **[to-spec](./to-spec/SKILL.md)** — Turn the current conversation into a spec and publish it to the project issue tracker — no interview, just synthesis of what you've already discussed.
- **[to-tickets](./to-tickets/SKILL.md)** — Break a plan, spec, or the current conversation into a set of tracer-bullet tickets, each declaring its blocking edges, published to the configured tracker — edges as text in one file per ticket locally, or native blocking links on a real tracker.
- **[triage](./triage/SKILL.md)** — Move issues and external PRs through a state machine of triage roles — categorise, verify, grill if needed, and write agent-ready briefs.
- **[wayfinder](./wayfinder/SKILL.md)** — Plan a huge chunk of work — more than one agent session can hold — as a shared map of decision tickets on your issue tracker, and resolve them one at a time until the way to the destination is clear.
- **[writing-beats](./writing-beats/SKILL.md)** — Writing, exploit — assemble raw material into a journey of beats, grounding each term before a beat leans on it.
- **[writing-fragments](./writing-fragments/SKILL.md)** — Writing, explore — mine raw fragments, no structure yet.
- **[writing-great-skills](./writing-great-skills/SKILL.md)** — Reference for writing and editing skills well — the vocabulary and principles that make a skill predictable.
- **[writing-shape](./writing-shape/SKILL.md)** — Writing, exploit — shape raw material into an article, paragraph by paragraph.

## Provenance

Upstream is [mattpocock/skills](https://github.com/mattpocock/skills); see
`LICENSE.mattpocock`.

This tree merges what used to be two diverging copies — `.agents/skills/` and a
bundled pack under `src/pycreditools/_skills_utils/skills/` — both removed in
favour of this one. Where the two disagreed the bundled pack won: it is the
newer generation, having renamed `review`→`code-review`,
`to-issues`→`to-tickets`, `to-prd`→`to-spec`, `ubiquitous-language`→
`domain-modeling`, `design-an-interface`→`codebase-design`, and dropped
`request-refactor-plan` and `qa`. Those seven superseded skills, and
`tdd/refactoring.md` (unreferenced once upstream moved refactoring out of the
TDD loop), are not carried here; they remain in git history at commit `cde59ed`
if you want one back.
