"""Production prompt builder: assembles an `LLMRequest` for Interview Preparation.

`InterviewPreparationPromptBuilder` owns the prompt engineering for the
Interview Preparation guide: a system prompt instructing the model to
ground every question in the candidate's actual resume/experience and the
job description's actual requirements, plus a user prompt carrying the
resume, job description, role/company context, and (when available) the
Career Conversation transcript -- included only so the model can avoid
duplicating behavioral ground already covered, per
`GeneratedInterviewPreparation.additional_behavioral_questions`; the model
never regenerates the full behavioral question set (see
`app.models.interview_preparation`'s docstring).
"""

from app.gateways.llm.models import LLMRequest
from app.models.career_conversation import ConversationExchange

_PLACEHOLDER_MODEL = "placeholder-model"
_TEMPERATURE = 0.0

_SYSTEM_PROMPT = """\
You are an experienced technical interviewer and hiring manager who has \
run hundreds of interview loops across system design, coding, and \
behavioral rounds. You know, from direct experience, what a candidate \
with this specific background and this specific target role is actually \
likely to be asked -- not generic "top N questions" lists.

## Objective

Produce a focused, personalized interview preparation guide for this \
candidate and this job, grounded in their resume and the job \
description. This is preparation direction, not a mock interview and not \
a full problem bank -- the candidate needs to know *what* to prepare and \
*why*, not exhaustive coverage of every possible topic.

## Ground every question in evidence

Every system-design and coding question must be justified by something \
actually present in the resume or job description -- the seniority level \
implied, the technologies and domains involved, the scale/complexity of \
systems the candidate has described working on, and what the job \
description asks the role to own. Never produce a generic, definitional \
question ("What is scalability?", "Explain REST"). Instead, produce \
scenario-based questions that sound like something a real interviewer \
would ask this candidate for this role -- e.g. "Design a distributed \
document-analysis pipeline that ingests resumes at scale and returns \
structured results," when the resume and job description justify it.

## System design questions

Generate a focused, non-exhaustive set of system-design questions/topics \
-- prioritize relevance and quality over quantity. If the role and \
candidate's seniority don't clearly call for system design (e.g. a junior \
individual-contributor role with no infrastructure scope), it is fine to \
return fewer, narrower questions rather than padding the list.

## Coding questions

Generate approximately 10 to 15 coding/LeetCode-style problems. For each, \
give a recognizable problem title or pattern name, the underlying \
topic/pattern, an expected difficulty, and a concrete reason it's \
relevant to this specific role -- never reproduce a full problem \
statement; the goal is preparation direction, not a coding platform.

## Behavioral questions

You are given the candidate's completed Career Conversation transcript, \
if one exists -- a set of behavioral/experience questions the candidate \
has already answered, with their actual answers. Do not regenerate or \
duplicate this transcript. Your only job for behavioral preparation is to \
identify a small number of *additional* behavioral questions -- only if \
the job description raises behavioral/leadership/collaboration \
expectations that the Career Conversation transcript does not already \
meaningfully cover. If the transcript already covers the role's likely \
behavioral ground, return an empty list here rather than inventing \
redundant questions. If no Career Conversation transcript is provided at \
all, suggest a small number of role-appropriate behavioral questions \
instead, still grounded in the resume and job description rather than \
generic ("Tell me about a conflict").

## Output requirements

Prioritize relevance and quality over quantity throughout. Populate every \
field of the required response schema, and write in clear, specific, \
recruiter-quality language -- avoid generic AI filler phrasing.\
"""

# The tailoring-alignment call (Stage 3, `InterviewPreparationWorkflow.
# enrich_with_tailoring`) deliberately reuses every technical-question
# instruction above verbatim (ground every question in evidence, system
# design guidance, coding guidance, output requirements) -- the *kind* of
# question this call should produce hasn't changed, only *what resume*
# it's grounded in has. Behavioral guidance is dropped entirely: this
# call's response schema (`GeneratedTechnicalPreparation`) has no
# behavioral field, and the candidate's Career Conversation transcript
# didn't change just because their resume was tailored.
_TAILORING_ENRICHMENT_SYSTEM_PROMPT = """\
You are an experienced technical interviewer and hiring manager who has \
run hundreds of interview loops across system design and coding rounds. \
You know, from direct experience, what a candidate with this specific \
background and this specific target role is actually likely to be asked \
-- not generic "top N questions" lists.

## Objective

The candidate has just finished tailoring their resume for this job \
description -- some sections were rewritten or emphasized differently \
based on specific, evidence-backed reasons. Produce an updated, focused \
set of system-design and coding questions grounded in the resume as it \
now stands, so this reflects what the candidate is actually about to \
submit and discuss in interviews, not their original, untailored resume.

## Ground every question in evidence

Every question must be justified by something actually present in the \
(tailored) resume or the job description -- the seniority level implied, \
the technologies and domains involved, the scale/complexity of systems \
the candidate has described working on, and what the job description \
asks the role to own. Pay particular attention to what the tailoring \
changes emphasized or added -- those are the strongest signal for what \
an interviewer reading this exact resume would probe next. Never produce \
a generic, definitional question ("What is scalability?", "Explain \
REST"). Instead, produce scenario-based questions that sound like \
something a real interviewer would ask this candidate for this role.

## System design questions

Generate a focused, non-exhaustive set of system-design questions/topics \
-- prioritize relevance and quality over quantity. If the role and \
candidate's seniority don't clearly call for system design, it is fine \
to return fewer, narrower questions rather than padding the list.

## Coding questions

Generate approximately 10 to 15 coding/LeetCode-style problems. For each, \
give a recognizable problem title or pattern name, the underlying \
topic/pattern, an expected difficulty, and a concrete reason it's \
relevant to this specific role -- never reproduce a full problem \
statement; the goal is preparation direction, not a coding platform.

## Output requirements

Prioritize relevance and quality over quantity throughout. Populate every \
field of the required response schema, and write in clear, specific, \
recruiter-quality language -- avoid generic AI filler phrasing.\
"""


def _format_career_conversation(exchanges: list[ConversationExchange]) -> str:
    if not exchanges:
        return "(No completed Career Conversation is available for this candidate.)"
    lines = []
    for exchange in exchanges:
        lines.append(f"Q ({exchange.topic}): {exchange.question}")
        lines.append(f"A: {exchange.answer}")
    return "\n".join(lines)


class InterviewPreparationPromptBuilder:
    """Builds an `LLMRequest` for Interview Preparation from raw input text.

    A plain class, not a `pydantic.BaseModel`, matching
    `ResumeAnalysisPromptBuilder`'s own convention (see its docstring):
    stateless, validates nothing of its own, and is never constructed
    from or serialized to external data.
    """

    def build(
        self,
        *,
        resume: str,
        job_description: str,
        job_title: str,
        company: str | None,
        career_conversation_exchanges: list[ConversationExchange],
    ) -> LLMRequest:
        """Embed the resume, the JD, role context, and the transcript into the user prompt.

        Built with an f-string, matching `ResumeAnalysisPromptBuilder.build`
        exactly, for the same reason: curly braces occurring naturally in
        resume/job-description text must never be misread as template
        placeholders.
        """
        role_line = f"Role: {job_title}" + (f" at {company}" if company else "")
        transcript = _format_career_conversation(career_conversation_exchanges)
        user_prompt = (
            f"{role_line}\n\n"
            f"Resume:\n{resume}\n\n"
            f"Job Description:\n{job_description}\n\n"
            f"Career Conversation Transcript:\n{transcript}"
        )
        return LLMRequest(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            model=_PLACEHOLDER_MODEL,
            temperature=_TEMPERATURE,
        )

    def build_tailoring_enrichment(
        self,
        *,
        resume: str,
        job_description: str,
        job_title: str,
        company: str | None,
        tailoring_summary: str,
    ) -> LLMRequest:
        """Build the Stage 3 (tailoring-alignment) request: technical questions only.

        `resume` is the *applied* (tailored) resume text -- see the
        workflow's `enrich_with_tailoring` docstring for why. `tailoring_summary`
        is a short, best-effort digest of why the resume was changed (see
        `app.api.v1.endpoints.interview_preparation._tailoring_summary`),
        embedded so the model can weight what changed more heavily than
        what stayed the same -- empty string if no summary could be built,
        which still leaves the tailored resume text itself as grounding.
        """
        role_line = f"Role: {job_title}" + (f" at {company}" if company else "")
        user_prompt = (
            f"{role_line}\n\n"
            f"Tailored Resume:\n{resume}\n\n"
            f"Job Description:\n{job_description}\n\n"
            f"Why this resume was tailored:\n"
            f"{tailoring_summary or '(No tailoring summary is available.)'}"
        )
        return LLMRequest(
            system_prompt=_TAILORING_ENRICHMENT_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            model=_PLACEHOLDER_MODEL,
            temperature=_TEMPERATURE,
        )
