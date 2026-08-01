"""First production prompt builder: assembles an `LLMRequest` for resume analysis.

`ResumeAnalysisPromptBuilder` exists to prove out the seam between
`prompts/` and `gateways/llm/`: it takes raw resume and job-description
text and embeds them, unmodified, into a readable template. It performs no
prompt engineering, no parsing of the resume, and no interpretation of the
job description — that logic will come later, once real prompting strategy
is decided.
"""

from app.gateways.llm.models import LLMRequest

_PLACEHOLDER_MODEL = "placeholder-model"
_PLACEHOLDER_TEMPERATURE = 0.0
_PLACEHOLDER_SYSTEM_PROMPT = "Placeholder system prompt."


class ResumeAnalysisPromptBuilder:
    """Builds an `LLMRequest` for resume analysis from raw input text.

    A plain class rather than a `pydantic.BaseModel`: this builder holds no
    state and validates nothing of its own — it is a stateless assembler of
    an `LLMRequest`, which is already the validated data contract. Modeling
    it as a `BaseModel` would add validation/serialization machinery this
    class has no use for, since nothing about it is ever constructed from
    external data (e.g. deserialized JSON) or serialized back out.
    """

    def build(self, resume: str, job_description: str) -> LLMRequest:
        """Embed `resume` and `job_description` into a readable prompt template.

        The two inputs are inserted into the template verbatim, with no
        cleaning, truncation, section extraction, or scoring. This is
        deliberately the simplest possible transformation from "two raw
        strings" to "a valid `LLMRequest`" — just enough to route real
        resume/job-description content through the gateway for the first
        time. Built with an f-string rather than `str.format()`, so that
        curly braces occurring naturally in resume or job-description text
        can't be misinterpreted as template placeholders. `model` and
        `temperature` are fixed placeholder constants because choosing a
        real model/temperature is a downstream configuration decision, not
        something a prompt builder should decide.
        """
        user_prompt = f"Resume:\n{resume}\n\nJob Description:\n{job_description}"
        return LLMRequest(
            system_prompt=_PLACEHOLDER_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            model=_PLACEHOLDER_MODEL,
            temperature=_PLACEHOLDER_TEMPERATURE,
        )
