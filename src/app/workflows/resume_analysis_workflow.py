"""First application workflow: orchestrates a single LLM call end to end.

`ResumeAnalysisWorkflow` composes three independently-developed
collaborators — a prompt builder, an `LLMGateway`, and a response parser —
into the sequence "build prompt, call gateway, parse response, return
result." It contains no prompting or parsing logic itself; it only knows
the *order* in which those steps happen.
"""

from app.gateways.llm.gateway import LLMGateway
from app.models.resume_analysis import ResumeAnalysisResult
from app.parsers.resume_analysis_response_parser import ResumeAnalysisResponseParser
from app.prompts.resume_analysis_prompt_builder import ResumeAnalysisPromptBuilder


class ResumeAnalysisWorkflow:
    """Orchestrates resume analysis by composing a prompt builder, gateway, and parser.

    All three collaborators are supplied by the caller (constructor
    injection) rather than constructed here. This keeps the workflow a pure
    orchestrator: it depends on the `ResumeAnalysisPromptBuilder` and
    `ResumeAnalysisResponseParser` *interfaces* (in this codebase, their
    concrete classes, since no protocol exists for them yet) and on the
    `LLMGateway` abstraction, but owns none of their implementation
    details. Callers can inject a `MockGateway` in development/tests and a
    real provider adapter in production, or swap in a different prompt
    builder or parser later, without changing this class — the same
    rationale already applied to injecting `LLMGateway` alone before this
    refactor.
    """

    def __init__(
        self,
        prompt_builder: ResumeAnalysisPromptBuilder,
        gateway: LLMGateway,
        response_parser: ResumeAnalysisResponseParser,
    ) -> None:
        """Store the three injected collaborators for use by `analyze`."""
        self._prompt_builder = prompt_builder
        self._gateway = gateway
        self._response_parser = response_parser

    async def analyze(self, resume: str, job_description: str) -> ResumeAnalysisResult:
        """Build a prompt, call the gateway, parse the response, and return the result.

        This method is deliberately just four steps with no branching,
        error handling, or interpretation of `resume`/`job_description`
        beyond passing them along: it delegates *what* a prompt looks like
        to `ResumeAnalysisPromptBuilder` and *how* a response becomes a
        `ResumeAnalysisResult` to `ResumeAnalysisResponseParser`. The
        workflow itself does not know — and should not need to know — how
        either of those collaborators does its job, only that they exist
        and run in this order. Both collaborators are currently
        placeholders (fixed prompt template, hardcoded result), so this
        method's observable behavior is unchanged from before the refactor
        aside from now returning a `ResumeAnalysisResult` instead of the
        raw `LLMResponse`.
        """
        request = self._prompt_builder.build(resume, job_description)
        response = await self._gateway.generate(request)
        return self._response_parser.parse(response)
