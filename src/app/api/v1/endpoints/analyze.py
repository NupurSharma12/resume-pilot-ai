"""First business endpoint: `POST /v1/analyze`.

Wires an HTTP request to `ResumeAnalysisWorkflow` and back. Contains no
business logic itself — it only translates between the API schema and the
workflow's inputs/outputs, and constructs the workflow's dependencies
(currently `MockGateway`, so no real LLM provider or API tokens are
required to exercise this endpoint).
"""

from fastapi import APIRouter, Depends

from app.api.v1.models.analyze_resume import AnalyzeResumeRequest, AnalyzeResumeResponse
from app.core.config import Settings, get_settings
from app.gateways.llm.gateway import LLMGateway
from app.gateways.llm.gemini_gateway import GeminiGateway
from app.gateways.llm.mock_gateway import MockGateway
from app.parsers.resume_analysis_response_parser import ResumeAnalysisResponseParser
from app.prompts.resume_analysis_prompt_builder import ResumeAnalysisPromptBuilder
from app.workflows.resume_analysis_workflow import ResumeAnalysisWorkflow

router = APIRouter()


def get_resume_analysis_workflow(
    settings: Settings = Depends(get_settings),
) -> ResumeAnalysisWorkflow:
    """Construct a `ResumeAnalysisWorkflow` wired with its current dependencies.

    A FastAPI dependency-provider function, not a module-level singleton or
    logic inside the route handler: this is the one place that decides
    *which* prompt builder, gateway, and parser the workflow uses for this
    endpoint. `ResumeAnalysisPromptBuilder` and `ResumeAnalysisResponseParser`
    are still fixed (they're still placeholders themselves, and this task
    doesn't touch them), but the gateway is now selected based on
    `settings.llm_provider`, itself obtained via `Depends(get_settings)`
    rather than imported and called directly — keeping this function's
    only source of configuration consistent with how the rest of the app
    reads settings (through the cached `get_settings` dependency, not ad
    hoc construction), and making it straightforward to override
    `get_settings` in tests via FastAPI's dependency-override mechanism.

    `"mock"` and `"gemini"` are handled explicitly, and any other value
    raises `ValueError` rather than silently falling back to a default
    provider: an unrecognized `llm_provider` almost certainly means a
    misconfigured environment, and failing loudly at request time (this
    function is re-evaluated per request, so a bad value is never
    latched-in past a config fix) is safer than quietly serving mock
    responses in what was meant to be a real-provider deployment, or vice
    versa.

    A new gateway (and workflow) instance is constructed per call rather
    than cached, since both `MockGateway` and `GeminiGateway` are cheap and
    stateless to construct — there is no cost or correctness reason to
    share instances across requests, and per-call construction keeps this
    function simple.
    """
    if settings.llm_provider == "mock":
        gateway: LLMGateway = MockGateway()
    elif settings.llm_provider == "gemini":
        gateway = GeminiGateway(settings)
    else:
        raise ValueError(f"Unknown llm_provider: {settings.llm_provider!r}")

    return ResumeAnalysisWorkflow(
        prompt_builder=ResumeAnalysisPromptBuilder(),
        gateway=gateway,
        response_parser=ResumeAnalysisResponseParser(),
    )


@router.post("/analyze", response_model=AnalyzeResumeResponse)
async def analyze_resume(
    payload: AnalyzeResumeRequest,
    workflow: ResumeAnalysisWorkflow = Depends(get_resume_analysis_workflow),
) -> AnalyzeResumeResponse:
    """Analyze a resume against a job description and return the result.

    The handler does exactly two things: call the injected workflow, and
    map its `ResumeAnalysisResult` onto the API's `AnalyzeResumeResponse`
    shape. The mapping is written out field by field rather than passing
    the domain model's dumped fields straight through, so that the API
    schema and the domain model are only *coincidentally* identical right
    now, not implicitly coupled — either can gain, rename, or drop a field
    later without the other silently breaking.
    """
    result = await workflow.analyze(
        resume=payload.resume,
        job_description=payload.job_description,
    )
    return AnalyzeResumeResponse(
        score=result.score,
        missing_skills=result.missing_skills,
        strengths=result.strengths,
        weaknesses=result.weaknesses,
    )
