"""First response parser: translates an `LLMResponse` into a `ResumeAnalysisResult`.

`ResumeAnalysisResponseParser` exists to prove out the seam between
`gateways/llm/` (raw model output) and `models/` (the domain result), before
any real extraction logic exists. It does not call an LLM and does not
parse `response.content` in any way — it returns a fixed, hardcoded
`ResumeAnalysisResult`, standing in for the extraction logic that will
replace it once a real prompting/response strategy is decided.
"""

from app.gateways.llm.models import LLMResponse
from app.models.resume_analysis import ResumeAnalysisResult

_PLACEHOLDER_SCORE = 82
_PLACEHOLDER_MISSING_SKILLS = ["Docker", "AWS"]
_PLACEHOLDER_STRENGTHS = ["C++", "System Design"]
_PLACEHOLDER_WEAKNESSES = ["Limited Python experience"]


class ResumeAnalysisResponseParser:
    """Parses an `LLMResponse` into a `ResumeAnalysisResult`.

    A plain class, not a `pydantic.BaseModel`: like the prompt builder, this
    parser holds no state and validates nothing of its own — it is a
    stateless translator between two already-validated data contracts
    (`LLMResponse` in, `ResumeAnalysisResult` out). There is nothing here
    that needs `BaseModel`'s validation or serialization behavior.
    """

    def parse(self, response: LLMResponse) -> ResumeAnalysisResult:
        """Return a hardcoded `ResumeAnalysisResult`, ignoring `response.content`.

        `response` is accepted so the method's public signature matches its
        eventual purpose (extracting a real result from real model output),
        but its content is intentionally unused for now: no JSON parsing,
        no text extraction, no validation against what the model actually
        said. This keeps the parser a pure placeholder — proving that a
        `ResumeAnalysisResult` can be produced from an `LLMResponse` at
        all — without guessing at a response format or extraction strategy
        that hasn't been decided yet.
        """
        return ResumeAnalysisResult(
            score=_PLACEHOLDER_SCORE,
            missing_skills=list(_PLACEHOLDER_MISSING_SKILLS),
            strengths=list(_PLACEHOLDER_STRENGTHS),
            weaknesses=list(_PLACEHOLDER_WEAKNESSES),
        )
