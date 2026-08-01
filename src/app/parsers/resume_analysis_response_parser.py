"""Temporary response parser: exposes Gemini's raw output through the domain model.

`ResumeAnalysisResponseParser` no longer returns a fully hardcoded result.
It now builds a `ResumeAnalysisResult` from the real `LLMResponse` coming
out of the gateway, but does so without any text parsing, regex, line
splitting, or inference: `response.content` is placed, verbatim and
unmodified, as the single element of `weaknesses`. This exists so the rest
of the application (the API endpoint, the workflow) can be exercised
end-to-end against a real Gemini response before a real
extraction/scoring strategy — which would need to interpret
`response.content` into a score and skill lists — has been designed.
"""

from app.gateways.llm.models import LLMResponse
from app.models.resume_analysis import ResumeAnalysisResult

_PLACEHOLDER_SCORE = 0


class ResumeAnalysisResponseParser:
    """Parses an `LLMResponse` into a `ResumeAnalysisResult`.

    A plain class, not a `pydantic.BaseModel`: like the prompt builder, this
    parser holds no state and validates nothing of its own — it is a
    stateless translator between two already-validated data contracts
    (`LLMResponse` in, `ResumeAnalysisResult` out). There is nothing here
    that needs `BaseModel`'s validation or serialization behavior.
    """

    def parse(self, response: LLMResponse) -> ResumeAnalysisResult:
        """Wrap `response.content` in a `ResumeAnalysisResult`, unparsed.

        `score` stays a fixed placeholder (`0`) and `missing_skills`/
        `strengths` stay empty: none of those can be honestly derived from
        raw model text without parsing it, which this parser deliberately
        does not do. `response.content` is placed as the sole element of
        `weaknesses` — not `strengths`, and not split across multiple
        fields — purely because `weaknesses` is where the task asked the
        full, unprocessed output to surface; this is not a claim that the
        content actually describes a weakness. The entire string is kept
        intact: no truncation, no line splitting, no regex extraction, no
        inference about what any part of it means. This is intentionally
        a temporary shape, meant to be replaced once real scoring/parsing
        logic exists to turn `response.content` into an actual score and
        skill lists.
        """
        return ResumeAnalysisResult(
            score=_PLACEHOLDER_SCORE,
            missing_skills=[],
            strengths=[],
            weaknesses=[response.content],
        )
