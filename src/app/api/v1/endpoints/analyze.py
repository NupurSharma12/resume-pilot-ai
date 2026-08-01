"""First business endpoint: `POST /v1/analyze`.

Wires an HTTP request to `ResumeAnalysisWorkflow` and back. Contains no
business logic itself — it only translates between the API schema and the
workflow's inputs/outputs, and constructs the workflow's dependencies
(currently `MockGateway`, so no real LLM provider or API tokens are
required to exercise this endpoint).
"""

from fastapi import APIRouter, Depends

from app.api.v1.models.analyze_resume import AnalyzeResumeRequest, AnalyzeResumeResponse
from app.gateways.llm.mock_gateway import MockGateway
from app.parsers.resume_analysis_response_parser import ResumeAnalysisResponseParser
from app.prompts.resume_analysis_prompt_builder import ResumeAnalysisPromptBuilder
from app.workflows.resume_analysis_workflow import ResumeAnalysisWorkflow

router = APIRouter()


def get_resume_analysis_workflow() -> ResumeAnalysisWorkflow:
    """Construct a `ResumeAnalysisWorkflow` wired with its current dependencies.

    A FastAPI dependency-provider function, not a module-level singleton or
    logic inside the route handler: this is the one place that decides
    *which* prompt builder, gateway, and parser the workflow uses for this
    endpoint. Today that's `ResumeAnalysisPromptBuilder`, `MockGateway`, and
    `ResumeAnalysisResponseParser` — all still placeholders themselves —
    but because this wiring lives in a single function referenced via
    `Depends`, swapping `MockGateway` for a real provider adapter later (or
    overriding it in tests via FastAPI's dependency-override mechanism)
    requires changing only this function, not the route handler.

    A new instance is constructed per call rather than reused, since all
    three collaborators are stateless — there is no cost or correctness
    reason to share instances across requests, and per-call construction
    keeps this function simple.
    """
    return ResumeAnalysisWorkflow(
        prompt_builder=ResumeAnalysisPromptBuilder(),
        gateway=MockGateway(),
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
