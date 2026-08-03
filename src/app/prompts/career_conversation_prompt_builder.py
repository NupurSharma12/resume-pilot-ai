"""Production prompt builder: assembles an `LLMRequest` for one Career Conversation turn.

`CareerConversationPromptBuilder` owns the prompt engineering for Evidence
Recovery: a system prompt that instructs Gemini to behave like an
experienced recruiter having a natural conversation with a candidate —
reasoning about the single biggest remaining evidence gap and asking one
question about it — plus a user prompt that grounds each turn in the
resume, job description, the resume analysis's identified gaps, and the
full conversation so far. It performs no gap analysis or stopping logic
itself; that judgment is Gemini's (for what to ask next) and the
workflow's (for whether to trust it — see
`CareerConversationWorkflow`). This class only assembles the request.
"""

from app.gateways.llm.models import LLMRequest
from app.models.career_conversation import ConversationExchange
from app.models.resume_analysis import ResumeAnalysisResult

_PLACEHOLDER_MODEL = "placeholder-model"
_TEMPERATURE = 0.4

_SYSTEM_PROMPT = """\
You are an experienced technical recruiter conducting a follow-up \
conversation with a candidate after reviewing their resume against a \
specific job description. You have already identified, through a prior \
structured analysis, where the resume's evidence is thin, missing, or \
unclear relative to what this job requires.

## Objective

Your goal is not to collect keywords. Your goal is to reconstruct the \
candidate's career — to uncover real experience the candidate has that \
their resume simply doesn't reflect well. A resume is a lossy, compressed \
summary of someone's actual work; your job is to have the kind of \
conversation a good recruiter has to decompress it, one topic at a time, \
so that whatever the candidate tells you can later be used to make their \
resume genuinely stronger for this specific job.

## Reason about the single biggest remaining gap

On every turn, you are given the resume, the job description, the prior \
structured analysis (missing skills per category, weaknesses, low-scoring \
categories, and recommended improvements), and the full conversation so \
far (every topic already covered, and what the candidate said about it). \
From all of that, identify the ONE remaining gap whose evidence would most \
improve this candidate's fit for THIS job if recovered — not the gap that \
is easiest to ask about, not a minor or cosmetic one, and never a topic \
already covered earlier in this conversation. Ask about that one gap only. \
Do not ask about more than one topic per turn, and do not ask a generic \
"tell me about yourself" question — every question must target a specific, \
identified gap.

## Ask like a recruiter, not an ATS

Never ask a yes/no, keyword-checklist question like "Have you worked with \
React?" or "Do you have Docker experience?". Instead, notice what the \
resume already says that is adjacent to the gap, and ask an open, \
curious, conversational question that invites the candidate to describe \
real work in their own words. For example:

- Instead of "Have you worked on React?", ask something like: "I noticed \
you've worked on internal tooling. Could you tell me more about the UI \
applications you've built? Which frontend technologies did you use?"
- Instead of "Have you worked on Docker?", ask something like: "How were \
your applications usually deployed? Were they packaged using Docker, \
deployed directly to servers, or orchestrated another way?"

Ground the question in something concrete already on the resume where \
possible (a project, a role, a responsibility) and use it as the opening \
to explore the gap — the candidate should feel like they are being drawn \
out by someone who read their resume carefully, not interrogated against \
a checklist.

## Only ask what materially matters for this job

Do not ask trivia, and do not ask about anything the job description \
doesn't actually care about. Every question must be traceable to a real, \
named gap between what this job requires and what the resume currently \
demonstrates. If you cannot identify a gap whose evidence would \
meaningfully change how strong this resume looks for this job, that is a \
signal you may be done, not a reason to ask a weaker question anyway.

## Deciding whether to continue or stop

Weigh what has already been recovered across the whole conversation so \
far against what the job description still requires. Set `should_stop` to \
true once no remaining gap is worth another question — either because the \
highest-impact gaps have already been explored, or because what remains \
is minor. Report your own genuine `confidence` (0-100) that enough \
high-impact evidence has been recovered to stop; do not inflate or deflate \
it to game any particular outcome — a downstream system, not you, decides \
the final cutoff, and it depends on you reporting this honestly.

When `should_stop` is true, `stop_reason` must explain briefly why (e.g. \
which gaps were resolved, or that no high-impact gaps remain), and \
`topic`, `evidence_goal`, `estimated_impact`, and `question` must all be \
null — there is no next question. When `should_stop` is false, all four \
of those fields must be populated and `stop_reason` must be null — you are \
asking exactly one new question. Never populate both a stop reason and a \
next question in the same turn.

## Output requirements

`topic` should be a short label for the gap this turn targets (a few \
words, e.g. "Frontend framework experience"). `evidence_goal` should state \
specifically what you're trying to learn and why it matters for this job \
description, in one or two sentences. `estimated_impact` should reflect \
how much recovering this evidence would strengthen this resume's fit for \
this job if the candidate can speak to it well. `question` should be the \
exact conversational message to show the candidate — natural, warm, \
specific, and never generic AI filler phrasing.\
"""


def _format_resume_analysis(analysis: ResumeAnalysisResult) -> str:
    """Render the parts of a resume analysis relevant to finding evidence gaps as plain text.

    Only the fields that describe *gaps* — skill-match scores and their
    missing skills, weaknesses, and recommended improvements — are
    included; `matching_projects` and `strengths` describe what's already
    well-covered, which is useful context but not what a gap-finding
    conversation is grounded in, so they're omitted to keep each turn's
    prompt focused. Plain text (not the model's `model_dump_json()`) so
    the LLM reads a recruiter-style briefing rather than a raw data
    dump, consistent with how `ResumeAnalysisPromptBuilder` embeds prose,
    not JSON, into its own user prompt.
    """
    lines = ["Skill category scores and gaps:"]
    for skill_match in analysis.skill_matches:
        missing = ", ".join(skill_match.missing_skills) if skill_match.missing_skills else "none"
        lines.append(f"- {skill_match.category}: {skill_match.score}/100. Missing: {missing}.")

    lines.append("\nWeaknesses identified in the prior analysis:")
    lines.extend(f"- {weakness}" for weakness in analysis.weaknesses)

    lines.append("\nRecommended resume improvements from the prior analysis:")
    for improvement in analysis.resume_improvements:
        lines.append(
            f"- [{improvement.section}] {improvement.recommendation} "
            f"(priority {improvement.priority})"
        )

    return "\n".join(lines)


def _format_history(history: list[ConversationExchange]) -> str:
    """Render the conversation so far as plain text, or a note that it hasn't started yet.

    Numbered so the model can easily refer to "the conversation so far"
    without ambiguity, and so it's obvious at a glance how many topics
    have already been covered.
    """
    if not history:
        return "No conversation has happened yet. This is the first turn."
    lines = []
    for index, exchange in enumerate(history, start=1):
        lines.append(f"{index}. Topic: {exchange.topic}")
        lines.append(f"   Question asked: {exchange.question}")
        lines.append(f"   Candidate's answer: {exchange.answer}")
    return "\n".join(lines)


class CareerConversationPromptBuilder:
    """Builds an `LLMRequest` for one Career Conversation turn from the session's context.

    A plain class rather than a `pydantic.BaseModel`, for the same reason
    as `ResumeAnalysisPromptBuilder`: it holds no state and validates
    nothing of its own, so there is no external data being deserialized
    or serialized through it.
    """

    def build(
        self,
        resume: str,
        job_description: str,
        resume_analysis: ResumeAnalysisResult,
        history: list[ConversationExchange],
    ) -> LLMRequest:
        """Embed the resume, job description, analysis gaps, and history into the user prompt.

        All grounding content is inserted verbatim (no cleaning,
        truncation, or summarization) with an f-string, for the same
        reason `ResumeAnalysisPromptBuilder.build` uses one: naturally
        occurring curly braces in resume/job-description/answer text
        can't be misread as template placeholders. `model` and
        `temperature` are fixed constants, matching that builder's
        pattern; `temperature` is set higher than the analysis prompt's
        `0.0` (which wants deterministic, grounded scoring) since this
        prompt asks for natural, varied, conversational phrasing turn to
        turn — but still low enough to stay grounded in the supplied gaps
        rather than drifting into generic small talk.
        """
        user_prompt = (
            f"Resume:\n{resume}\n\n"
            f"Job Description:\n{job_description}\n\n"
            f"Prior Resume Analysis:\n{_format_resume_analysis(resume_analysis)}\n\n"
            f"Conversation so far:\n{_format_history(history)}"
        )
        return LLMRequest(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            model=_PLACEHOLDER_MODEL,
            temperature=_TEMPERATURE,
        )
