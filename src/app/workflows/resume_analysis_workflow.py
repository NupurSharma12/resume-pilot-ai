"""First application workflow: orchestrates a single LLM call.

`ResumeAnalysisWorkflow` exists to prove out the orchestration seam between
`workflows/` and `gateways/llm/` before any real prompting, parsing, or
scoring logic is written. It performs exactly one `LLMGateway.generate`
call with placeholder content and hands the result back unchanged.
"""

from app.gateways.llm.gateway import LLMGateway
from app.gateways.llm.models import LLMRequest, LLMResponse

_PLACEHOLDER_MODEL = "placeholder-model"
_PLACEHOLDER_TEMPERATURE = 0.0
_PLACEHOLDER_SYSTEM_PROMPT = "Placeholder system prompt."
_PLACEHOLDER_USER_PROMPT = "Placeholder resume analysis prompt."


class ResumeAnalysisWorkflow:
    """Orchestrates resume analysis by delegating a single call to an `LLMGateway`.

    The workflow depends on an `LLMGateway` supplied by its caller
    (constructor injection) rather than constructing one itself. This keeps
    the workflow provider-agnostic and testable: callers can inject
    `MockGateway` in development/tests and a real provider adapter in
    production without changing this class. Instantiating a gateway inside
    the workflow would hardcode a provider choice here, which belongs to
    application wiring/composition, not orchestration logic.
    """

    def __init__(self, gateway: LLMGateway) -> None:
        """Store the injected gateway for use by `analyze`."""
        self._gateway = gateway

    async def analyze(self, resume: str, job_description: str) -> LLMResponse:
        """Run a single placeholder LLM call and return its response unchanged.

        `resume` and `job_description` are accepted now so the method's
        public signature matches its eventual purpose, but their content is
        intentionally ignored: this workflow does not yet build prompts
        from them, parse the model's output, or score anything — it only
        proves that a workflow can obtain a gateway via dependency
        injection and call it. Prompt construction, parsing, and scoring
        are deliberately left for a later change, once agents exist to own
        that logic.
        """
        request = LLMRequest(
            system_prompt=_PLACEHOLDER_SYSTEM_PROMPT,
            user_prompt=_PLACEHOLDER_USER_PROMPT,
            model=_PLACEHOLDER_MODEL,
            temperature=_PLACEHOLDER_TEMPERATURE,
        )
        return await self._gateway.generate(request)
