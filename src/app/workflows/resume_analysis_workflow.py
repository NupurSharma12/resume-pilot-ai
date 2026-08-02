"""First application workflow: orchestrates a single LLM call end to end.

`ResumeAnalysisWorkflow` composes two independently-developed
collaborators — a prompt builder and an `LLMGateway` — into the sequence
"build prompt, call the gateway for structured output, return result." It
contains no prompting logic itself; it only knows the *order* in which
those steps happen.
"""

from app.gateways.llm.gateway import LLMGateway
from app.models.resume_analysis import ResumeAnalysisResult
from app.prompts.resume_analysis_prompt_builder import ResumeAnalysisPromptBuilder


class ResumeAnalysisWorkflow:
    """Orchestrates resume analysis by composing a prompt builder and gateway.

    Both collaborators are supplied by the caller (constructor injection)
    rather than constructed here. This keeps the workflow a pure
    orchestrator: it depends on the `ResumeAnalysisPromptBuilder`
    interface (in this codebase, its concrete class, since no protocol
    exists for it yet) and on the `LLMGateway` abstraction, but owns none
    of their implementation details. Callers can inject a `MockGateway` in
    development/tests and a real provider adapter in production, or swap
    in a different prompt builder later, without changing this class.

    There is no longer a separate response-parser collaborator: now that
    `LLMGateway.generate_structured` returns a validated instance of a
    caller-supplied Pydantic model directly (via Gemini's native
    structured output), there is no raw text response left for a parser
    to translate — the gateway itself produces the domain object. The
    `parsers` package and `ResumeAnalysisResponseParser` still exist, just
    unused by this workflow now.
    """

    def __init__(
        self,
        prompt_builder: ResumeAnalysisPromptBuilder,
        gateway: LLMGateway,
    ) -> None:
        """Store the two injected collaborators for use by `analyze`."""
        self._prompt_builder = prompt_builder
        self._gateway = gateway

    async def analyze(self, resume: str, job_description: str) -> ResumeAnalysisResult:
        """Build a prompt, request structured output, and return the result.

        This method is deliberately just two steps with no branching,
        error handling, or interpretation of `resume`/`job_description`
        beyond passing them along: it delegates *what* a prompt looks like
        to `ResumeAnalysisPromptBuilder`, and delegates producing a
        validated `ResumeAnalysisResult` to the gateway's
        `generate_structured`, passing `ResumeAnalysisResult` itself as
        the target type. The workflow itself does not know — and should
        not need to know — how the prompt is built or how the gateway
        gets a `ResumeAnalysisResult` out of the underlying model; it only
        knows these two steps happen in this order.
        """
        request = self._prompt_builder.build(resume, job_description)
        return await self._gateway.generate_structured(request, ResumeAnalysisResult)
