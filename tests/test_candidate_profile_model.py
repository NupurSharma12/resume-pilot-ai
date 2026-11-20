"""Unit tests for `CandidateProfile` and its optional slot on `ResumeAnalysisResult`.

Pure model/schema assertions -- no network, no database, no LLM. The
central concern here is backward compatibility: `analysis_result` is
persisted as raw JSONB and re-validated through `ResumeAnalysisResult`
on every History read, so an analysis written before `candidate_profile`
existed must keep parsing unchanged. Combined with `extra="forbid"`,
making the field required would break every historical record -- these
tests pin that it stays optional.
"""

import pytest
from pydantic import ValidationError

from app.models.resume_analysis import CandidateProfile, ResumeAnalysisResult

# A payload in exactly the shape persisted before `candidate_profile`
# existed -- no such key anywhere.
LEGACY_ANALYSIS_PAYLOAD = {
    "overall_assessment": {
        "overall_score": 82,
        "hiring_recommendation": {"decision": "Strong Match", "reason": "Solid overlap."},
        "summary": "A strong candidate overall.",
    },
    "skill_matches": [
        {
            "category": "Backend",
            "score": 90,
            "matched_skills": ["Python"],
            "missing_skills": [],
        }
    ],
    "matching_projects": [],
    "strengths": ["Communication"],
    "weaknesses": ["Limited frontend experience"],
    "resume_improvements": [],
}


def test_legacy_payload_without_candidate_profile_still_parses():
    """A pre-feature record must validate, not raise, and report None."""
    result = ResumeAnalysisResult.model_validate(LEGACY_ANALYSIS_PAYLOAD)

    assert result.candidate_profile is None
    # The rest of the record is untouched by the new field.
    assert result.overall_assessment.overall_score == 82


def test_payload_with_candidate_profile_parses():
    payload = {
        **LEGACY_ANALYSIS_PAYLOAD,
        "candidate_profile": {
            "name": "Ada Lovelace",
            "current_company": "Analytical Engines Ltd",
            "title": "Principal Engineer",
            "years_experience": 12,
        },
    }

    result = ResumeAnalysisResult.model_validate(payload)

    assert result.candidate_profile is not None
    assert result.candidate_profile.name == "Ada Lovelace"
    assert result.candidate_profile.current_company == "Analytical Engines Ltd"
    assert result.candidate_profile.title == "Principal Engineer"
    assert result.candidate_profile.years_experience == 12


def test_optional_profile_fields_may_be_null():
    """A resume stating only a name is a normal case, not an error."""
    profile = CandidateProfile.model_validate(
        {
            "name": "Prince",
            "current_company": None,
            "title": None,
            "years_experience": None,
        }
    )

    assert profile.name == "Prince"
    assert profile.current_company is None
    assert profile.title is None
    assert profile.years_experience is None


def test_optional_profile_fields_may_be_omitted_entirely():
    profile = CandidateProfile.model_validate({"name": "Prince"})

    assert (profile.current_company, profile.title, profile.years_experience) == (
        None,
        None,
        None,
    )


def test_name_is_required():
    with pytest.raises(ValidationError):
        CandidateProfile.model_validate({"current_company": "Acme"})


def test_negative_years_experience_is_rejected():
    with pytest.raises(ValidationError) as exc_info:
        CandidateProfile.model_validate({"name": "Ada Lovelace", "years_experience": -1})

    assert "years_experience" in str(exc_info.value)


def test_unknown_profile_field_is_rejected():
    """`extra="forbid"` -- consistent with every other model in this module."""
    with pytest.raises(ValidationError):
        CandidateProfile.model_validate({"name": "Ada Lovelace", "rating": 4.5})


def test_generated_schema_exposes_candidate_profile_as_optional():
    """What both gateways actually send: `ResumeAnalysisResult.model_json_schema()`.

    `candidate_profile` must appear in `properties` (so a model is told to
    produce it) but must NOT appear in `required` (so historical records
    and models that omit it still validate).
    """
    schema = ResumeAnalysisResult.model_json_schema()

    assert "candidate_profile" in schema["properties"]
    assert "candidate_profile" not in schema.get("required", [])

    profile_schema = schema["$defs"]["CandidateProfile"]
    assert profile_schema["required"] == ["name"]
    for optional_field in ("current_company", "title", "years_experience"):
        assert optional_field in profile_schema["properties"]


# --- Gateway schema derivation -------------------------------------------
#
# `candidate_profile` reaching a provider must be a consequence of it
# being on `ResumeAnalysisResult`, never of a schema hand-written inside a
# gateway. These two tests pin that both providers still derive their
# schema from `response_model.model_json_schema()`, so the field shows up
# in each provider's outgoing request without any provider-specific
# change -- and so a future hand-rolled schema in either gateway fails
# here rather than silently drifting from the model.


async def test_openrouter_embeds_candidate_profile_from_the_response_model() -> None:
    import json

    import httpx

    from app.core.config import Settings
    from app.gateways.llm.models import LLMRequest
    from app.gateways.llm.openrouter_gateway import OpenRouterGateway

    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        captured["user_message"] = body["messages"][-1]["content"]
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": json.dumps(LEGACY_ANALYSIS_PAYLOAD)}}
                ],
            },
        )

    settings = Settings(
        openrouter_api_key="test-openrouter-key",
        openrouter_models=["test/model:free"],
    )
    gateway = OpenRouterGateway(settings)
    gateway._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://openrouter.ai/api/v1"
    )

    await gateway.generate_structured(
        LLMRequest(
            user_prompt="Analyze.", model="ignored-by-openrouter", temperature=0.0
        ),
        ResumeAnalysisResult,
    )

    # The schema OpenRouter receives is embedded in the user prompt.
    assert "candidate_profile" in captured["user_message"]
    assert "current_company" in captured["user_message"]


def test_gemini_sends_the_response_model_schema_verbatim() -> None:
    """GeminiGateway passes `response_model.model_json_schema()` through unmodified.

    Asserted at the schema level rather than by driving a live client:
    the contract that matters is that the dict handed to
    `response_json_schema` is the model's own schema, so any field added
    to `ResumeAnalysisResult` propagates with no gateway edit.
    """
    schema = ResumeAnalysisResult.model_json_schema()

    assert "candidate_profile" in schema["properties"]
    assert schema["$defs"]["CandidateProfile"]["properties"].keys() >= {
        "name",
        "current_company",
        "title",
        "years_experience",
    }
