"""In-process registry of generated suggestion plans, keyed by `plan_id`.

Mirrors `ConversationSessionStore` (`app.sessions.conversation_session`)
deliberately, both in shape and in scope: a plain `dict`, attached once to
`app.state` in `create_app`, injected via a FastAPI dependency. This is
what makes the apply step trustworthy — see
`docs/features/interactive-tailored-resume.md`: a client selecting
suggestions by id, or editing a suggestion's text, must be checked
against what the backend *actually generated and validated*, not
whatever the client claims a suggestion was. Without a server-side
record of the plan, the apply endpoint would have no choice but to trust
client-supplied suggestion content — exactly the "arbitrary client-
supplied evidence as trusted evidence" this feature must not do.

A `StoredPlan` bundles the `SuggestionPlan` together with the exact
`StructuredResume` and `EvidenceStore` it was generated against. Both are
needed again at apply time — not just the plan — for two reasons:
`SuggestionApplier` must re-anchor every suggestion's `target_item_id`
against the *same* structure it was planned against, and revalidating a
user-edited suggestion (see `app.evidence.suggestion_validator`) needs
the real evidence content, not just the ids. Storing this bundle avoids
asking the apply endpoint to resend the resume, job description, and
conversation history just to reconstruct it, and avoids re-parsing the
resume text a second time in a way that could ever drift from the first.

`job_description` is stored for the same reason: the post-apply
re-analysis endpoint (`POST .../reanalyze`, see
`docs/features/postapply-analysis-loop.md`) must compare the resume
against the *same* job description this plan was generated against, not
whatever a client happens to send at reanalyze time — a client-supplied
job description would let the "before" and "after" halves of a
comparison silently diverge. This is the one piece of that endpoint's
required context this store didn't already carry.

Everything here is `frozen=True` — nothing mutates a stored plan in
place, only stores a new one (`save`) or reads one back (`get`). No
expiry, no persistence, no cross-process sharing: plans live only in
this process's memory and are lost on restart, the same explicit scope
boundary `ConversationSessionStore` already documents — a real store
(Redis, a database) is required before this can run behind multiple
worker processes or survive a restart.
"""

from dataclasses import dataclass

from app.models.evidence_store import EvidenceStore
from app.models.resume_structure import StructuredResume
from app.models.tailoring_suggestions import SuggestionPlan


@dataclass(frozen=True)
class StoredPlan:
    """A generated `SuggestionPlan` plus the exact context it was generated against."""

    plan: SuggestionPlan
    structured_resume: StructuredResume
    evidence_store: EvidenceStore
    job_description: str


class TailoringPlanStore:
    """In-memory, single-process registry of generated suggestion plans."""

    def __init__(self) -> None:
        self._plans: dict[str, StoredPlan] = {}

    def save(self, stored_plan: StoredPlan) -> None:
        """Store (or overwrite) `stored_plan` under its plan's own `plan_id`."""
        self._plans[stored_plan.plan.plan_id] = stored_plan

    def get(self, plan_id: str) -> StoredPlan | None:
        """Return the stored plan for `plan_id`, or `None` if it doesn't exist (or never did)."""
        return self._plans.get(plan_id)
