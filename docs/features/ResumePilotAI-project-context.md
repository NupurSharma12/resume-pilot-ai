ResumePilotAI — Project Context & Continuation Brief

Purpose

ResumePilotAI is a resume-tailoring product being built to help a user take an existing resume and a target job description, recover missing evidence through a recruiter-style conversation, generate grounded tailoring suggestions, let the user selectively preview/apply those suggestions, preserve document fidelity where possible, re-analyze the result, and eventually maintain durable history.

Guiding principle:

Do not blindly rewrite the resume. Understand the existing resume, identify gaps against the JD, recover missing evidence, propose small understandable changes, let the user choose them, preview exactly what will change, apply in phases, and produce a genuinely usable final resume.

The user intends to use ResumePilotAI personally for job applications, so output quality and usability are more important than adding lots of features.

1. Product journey

Upload Resume
    ↓
Upload Job Description
    ↓
Resume Analysis
    ↓
Career Conversation
    ↓
Tailoring Suggestions
    ↓
Select / Deselect Suggestions
    ↓
Preview Changes
    ↓
Apply Now
    ↓
Re-analyze Updated Resume
    ↓
Continue Tailoring if needed
    ↓
Final Preview
    ↓
Download Resume
    ↓
Return later / History

The product should feel like an iterative resume optimization tool, not a one-shot AI rewrite service.

2. Important product decisions

Do not simply rewrite the entire resume

The user explicitly preferred:

append/update rather than indiscriminate rewriting

small actionable changes

understandable suggestions

user control over what is retained

preview before applying

phased application of changes

The UI should explain what will be added, updated, strengthened, or removed, where it happens, and why it is suggested, while remaining scan-first and avoiding information overload.

Suggestions must be atomic

If four independent pieces of evidence apply to the same resume section, they should appear as four independently selectable suggestions.

Example:

formal people-management responsibilities

AI-native tooling / Responsible AI

production incident / reliability experience

hiring / interviewing / mentoring

The user may want 2 of 4, not all 4.

Preview must come before Apply

Desired flow:

Review Suggestions
→ Preview Changes
→ Apply Now
→ Final Resume

Selecting suggestions must not silently apply them.

Preview should be GitHub/code-review style

Desired comparator:

two columns

Original | Proposed

red/green change treatment

only changed hunks/lines

small surrounding context

section-by-section navigation

read-only

clear mapping of where each suggestion lands

3. Current implemented feature set

The product currently has:

Resume upload

JD upload

Resume analysis

Career Conversation

Evidence recovery

Tailoring suggestion generation

Atomic suggestion selection

Suggestion conflict handling

Preview-first tailoring workflow

GitHub-style side-by-side diff

Phased apply

Applied/greyed suggestion state

Undo/UI-state handling

TXT/Markdown/PDF/DOCX export paths

Frontend session persistence

Extensive automated unit/integration testing

Interview preparation is explicitly not needed before deployment. It will be picked up after deployment.

4. Career Conversation

Career Conversation is a recruiter-style conversation intended to recover evidence missing or insufficiently explicit in the resume.

Areas already explored:

people management

live-site reliability / incident response

AI-native engineering tools and Responsible AI

cross-team dependency management

architectural strategy

Examples of captured evidence:

People management

The user has managed teams and mentored engineers, including performance management and career development at Labellerr, and has been interviewing/mentoring for roughly five years.

Production reliability

At Adobe:

customer crash reports/escalations

crash dump investigation

local reproduction

C++ debugging

root cause analysis

QA/Product collaboration

stability treated as release-critical

At OpenText:

production issues

security vulnerabilities

platform defects

incident triage

impact assessment

fixes

QA validation

safe releases

retrospectives/root-cause discussions

The user was explicitly honest that they have not personally owned tools such as Azure Monitor/Datadog or formal DRI/on-call rotations.

AI-native tools

At Labellerr:

encouraged AI-assisted development

Claude and CodeRabbit for coding/reviews/debugging/productivity

AI/computer vision collaboration

human ownership and review of AI output

Responsible AI philosophy:

human oversight

avoid exposing sensitive customer data to external AI services

validate AI-generated code

security/quality remain engineering responsibilities

Cross-team leadership

At Labellerr:

customers

frontend

backend

AI engineer

founders

product

API contracts

estimates

implementation trade-offs

code review

delivery alignment

5. Resilience work completed

Three important resilience issues were investigated and fixed.

500 error

Root cause:

CareerConversationWorkflow.submit_answer mutated the session by recording the answer before successfully obtaining the next LLM decision.

If the LLM failed, the answer was consumed but there was no replacement question and the session was not completed.

Fix:

_request_decision()  → pure
_apply_decision()    → mutation only after valid decision

This prevents partial/irreversible state mutation.

409 conflict

There were exactly two backend 409 sources:

already-completed fast path

in-lock no-open-question recheck

Both were correct.

Frontend now classifies 409 as a conflict and refetches/resumes appropriately.

Missing CTA after refresh

Root cause:

DashboardLayout had no hydration gate.

On refresh it briefly rendered the “nothing exists” state before restored state arrived.

Fix:

Central hydration gate in DashboardLayout, rather than patching individual pages.

6. Resume session architecture

Frontend session architecture:

ResumeSessionProvider
        ↓
storage interface
        ↓
sessionStorage

Persisted state includes:

plan

plan status

selections

custom instructions

edited suggestion text

final resume

validation report

available formats

source format

Storage schema was bumped so old sessions are discarded cleanly when incompatible.

Frontend persistence is not durable backend history.

7. Tailoring Engine architecture

Pipeline:

ResumeStructureParser
    ↓
StructuredResume
    ↓
EvidenceStoreBuilder
    ↓
TailoringSuggestionWorkflow
    ↓
TailoringPlanStore
    ↓
SuggestionApplier
    ↓
ExportService

ResumeStructureParser

Raw resume text → structured, addressable sections/items with stable IDs.

EvidenceStoreBuilder

Evidence is associated with individual resume items rather than only whole sections.

TailoringSuggestionWorkflow

One Planner call generates the plan.

Then per-suggestion Rewrite Engine calls are scoped to only that suggestion's approved evidence.

TailoringPlanStore

In-memory trust boundary.

Apply/export do not trust client-supplied suggestion content. They validate suggestion IDs against what the backend actually generated.

SuggestionApplier

Deterministically applies selected suggestions and detects conflicts.

ExportService

Renders final StructuredResume to:

TXT

Markdown

DOCX

PDF

8. Tailoring suggestion model

Suggestions are anchored to real target_item_ids.

Supported operations include:

append

insert

update

replace

add_emphasis

remove

User-facing mapping:

append / insert   → Add
update / replace  → Update
add_emphasis      → Strengthen
remove            → Remove

This mapping is centralized in OPERATION_ACTION_LABELS.

9. Suggestion conflict design

Previous problem: every pair of suggestions targeting the same resume item was treated as conflicting. That was too coarse.

New rules:

two rewrites on same item → conflict

rewrite + append on same item → conflict

two appends on same item → composable

two same-side insertions → conflict

unrelated edits → no conflict

Shared conflict implementation is used by:

TailoringSuggestionWorkflow

SuggestionApplier

DocxDocumentEditor

Multiple appends are composed deterministically in plan-generation order.

Planner prompt was strengthened to avoid bundling multiple independent facts into one suggestion.

10. Suggestion UI philosophy

Stage 2 was redesigned into a scan-first “resume coach” interface.

Default card shows only:

section

one-line human summary

Why?

Impact

selection checkbox

Everything else is progressive disclosure.

Independent disclosure controls:

Evidence

Preview Change

View Current Resume Text

Evidence is currently label-only because the API deliberately does not expose raw evidence snippets.

The user prefers evidence to be visually lightweight rather than dumping evidence text into the main screen.

11. GitHub-style comparator

Current comparator:

SideBySideDiff.tsx

resumeSectionDiff.ts

It displays:

Original                  Proposed
----------------------    ----------------------
old text                  new text
- removed                 + added

Used for:

individual suggestion preview

combined preview

Only changed hunks plus small context are shown.

Limitations:

genuine replacements may show whole sentence removed/added

append gets better sub-sentence handling

unusual section heading layouts can affect display-only section matching

No fabricated changes are derived from suggestion reasons.

12. Preview/apply/phased workflow

Current UX:

Review Suggestions
    ↓
Preview Changes
    ↓
Apply Now
    ↓
Final Resume
    ↓
Continue Editing

Applied suggestions are greyed/locked.

Phased workflow:

Phase 1:
select A + B
→ preview
→ apply

Phase 2:
select C + D
→ preview
→ apply

Important limitation:

There is no real backend revert endpoint yet.

“Undo” is UI-state-level:

it prevents a suggestion from being included in the next preview/apply

it cannot retroactively modify an already downloaded/applied document

13. DOCX fidelity

High-fidelity DOCX editing architecture was built under:

app/document_editing/

Files include:

node.py

docx_nodes.py

docx_structure_mapper.py

docx_document_editor.py

Architecture:

Original DOCX
    ↓
DocxStructureMapper
    ↓
StructuredResume + item_id → live DOCX node map
    ↓
DocxDocumentEditor
    ↓
Mutate original DOCX OOXML
    ↓
Edited DOCX

Exact fidelity is achieved for:

append

insert

remove

For update/replace/add_emphasis:

paragraph formatting is preserved

mixed inline formatting inside a paragraph may collapse to the first run’s style

28 DOCX tests were added around formatting-rich fixtures, bold/italic/color/size, tables, headers, footers, and preservation of unrelated content.

Integration gap

The DOCX fidelity engine was initially not reachable from the real export endpoint.

Required integration:

retain original DOCX bytes

create a bytes store

use DocxStructureMapper when source is DOCX

route export through DocxDocumentEditor

Do not claim formatting fidelity until this is wired end-to-end.

14. PDF decision

PDF formatting preservation is not promised.

PDF → DOCX conversion cannot honestly guarantee high fidelity.

Therefore:

DOCX source → use DOCX fidelity path

PDF source → do not claim original formatting preservation

regenerated outputs should be labeled honestly

Current fidelity labels:

TXT / Markdown
→ APPROXIMATE_STYLE

Regenerated DOCX / PDF
→ REGENERATED_TEMPLATE

The product should be upfront about this limitation.

15. Backend persistence/history issue

Current backend stores are in-memory Python dictionaries:

ConversationSessionStore
TailoringPlanStore

They are unpersisted.

A real failure exposed this:

frontend restored a tailoring plan from sessionStorage

backend no longer had the corresponding plan/session

Apply returned 404

Investigation also found multiple backend processes had been bound to port 8000 during development. One process contained the session; another did not.

The deeper architectural truth is:

Any backend restart, crash, reload, redeploy, or process replacement can lose in-memory workflow state.

Frontend recovery can regenerate a stale tailoring plan only if the career conversation is still available.

Long-term decision

Persistent backend storage should eventually persist:

career conversation history

tailoring plans

selected suggestions

edited suggestion text

applied phases

resume versions

analysis versions

final tailored resume state

relevant export metadata

Frontend sessionStorage should become a cache/working state, not the permanent source of truth.

16. Post-apply analysis loop

Planned next feature:

Apply
 ↓
Re-analyze updated resume against same JD
 ↓
Compare before vs after
 ↓
Show improvement
 ↓
Show remaining gaps
 ↓
Show possible regressions
 ↓
Continue Tailoring

The user specifically wants the system to verify whether tailoring actually improves the resume/JD match.

This turns ResumePilotAI into an optimization loop rather than a rewriting tool.

17. Browser/E2E testing

Manual UI testing is not considered reliable/available for this project.

Therefore browser-level automated testing is a deployment prerequisite.

Golden Playwright flow:

Resume upload
→ JD upload
→ analysis
→ career conversation
→ tailoring suggestions
→ selection
→ GitHub-style preview
→ Apply
→ updated resume
→ re-analysis
→ final preview
→ download

Additional scenarios:

refresh during upload

refresh during analysis

refresh during conversation

refresh during tailoring review

stale plan/session behavior

404 recovery

409 handling

phased apply

applied/greyed suggestions

reselect and re-preview

comparator behavior

downloads

DOCX path

18. Historical automated test milestones

These are historical checkpoints; rerun the current suite before deployment.

Resilience work:

Backend 131/131

Frontend 62/62

Upload fixes:

Frontend 118/118

Suggestion UI:

Frontend 152/152

DOCX fidelity:

Backend 195/195

Atomic suggestion conflicts:

Backend 214/214

Frontend 179/179

GitHub-style comparator:

Frontend 235/235

Backend remained 214/214

Current numbers must be rechecked after subsequent changes.

19. Known limitations

Backend workflow state is not durable.

Full conversation history persistence is not implemented.

DOCX fidelity engine needs real-flow integration.

PDF fidelity cannot be guaranteed.

Planner atomic decomposition is strongly prompted but not mathematically guaranteed.

Conflict detection is operation-level because there are no character-offset spans.

Undo is UI-state-only.

Evidence display contains labels rather than verbatim evidence snippets because evidence content is internal to the backend API.

No headless browser was initially available during some UI work; browser E2E is therefore still an important next step.

20. Documentation

Relevant docs:

docs/features/browser-e2e-golden-journey.md
docs/features/post-apply-analysis-loop.md
docs/architecture/persistent-workflow-state.md
docs/features/high-fidelity-docx-editing.md
docs/features/interactive-tailored-resume.md
docs/features/career-conversation-resilience.md

The first three were also created as standalone Markdown files for project context.

21. Recommended implementation sequence

The agreed sequence is:

1. Full Playwright browser E2E

Validate the real product journey from upload to final download.

2. Post-apply analysis loop

Implement:

re-analysis

before/after comparison

improvement summary

remaining gaps

continue tailoring

3. Persistent backend workflow/history

Implement durable storage for:

conversations

tailoring plans

resume versions

analysis versions

applied phases

This should be picked up before serious long-lived deployment because the user wants to return later and maintain history.

4. Complete DOCX fidelity integration

Ensure the real product path uses the high-fidelity editor for DOCX uploads.

5. Final real-stack smoke test

6. Deploy

After deployment

Interview preparation can be built.

It is explicitly not a pre-deployment priority.

22. Deployment blockers

Treat these as blockers for a trustworthy deployment:

Full browser E2E golden journey

Post-apply analysis loop

DOCX fidelity wired into real flow

Persistent backend history/storage

Final real-stack smoke test

23. Git/branch discipline

The user prefers to checkpoint completed work before moving to the next major feature.

Preferred workflow:

finish coherent feature

run tests

commit

create branch for next major feature

implement

test

commit/merge

Do not mix unrelated feature changes into an existing commit.

24. Product north star

I upload my existing resume.
        ↓
The system analyzes it against the job.
        ↓
It asks me only about evidence it cannot confidently recover.
        ↓
It proposes small, grounded changes.
        ↓
I decide what I want.
        ↓
I see exactly what will change before anything is applied.
        ↓
I can apply changes in phases.
        ↓
The system re-analyzes the improved resume.
        ↓
I can keep iterating until satisfied.
        ↓
I download a genuinely usable resume.
        ↓
I can return later and see my conversation,
resume versions, tailoring history, and analyses.

Quality principles:

User control

Evidence-grounded AI

Transparent changes

No destructive blind rewriting

Honest fidelity claims

Recoverability

Durable history

Automated browser-level confidence

Final output that is actually usable for job applications