// Hardcoded input for proving the end-to-end pipeline (frontend -> FastAPI
// -> Gemini -> frontend) without building file upload yet. Standing in for
// what a recruiter would eventually upload; this file is the only thing
// that needs to change once real uploads exist — nothing downstream reads
// input text directly, only `ResumeAnalysisResult` (see lib/api.ts).

export const SAMPLE_RESUME = `Nupur Sharma
Senior Product Manager

Experience:
Adobe — Senior Product Manager (7 years)
- Led the product strategy for a suite of enterprise SaaS collaboration tools used by 50,000+ business customers.
- Directly managed a cross-functional pod of 12 engineers, 2 designers, and a data analyst spread across three time zones.
- Owned the roadmap and P&L for a $40M ARR product line, driving 18% YoY growth through prioritized feature investment.
- Partnered with enterprise sales and customer success to reduce churn by 9% via targeted retention features.
- Mentored two associate product managers, both promoted within 18 months.
- Presented quarterly business reviews directly to VP- and SVP-level stakeholders.

Previous — Product Manager, mid-size B2B SaaS startup (6 years)
- Shipped a product-led growth onboarding flow that increased trial-to-paid conversion by 22%.
- Worked closely with engineering on system architecture tradeoffs for a multi-tenant platform migration.
- Wrote detailed PRDs and ran weekly stakeholder syncs across support, marketing, and engineering.

Skills: Product strategy, roadmapping, cross-functional leadership, B2B SaaS, stakeholder management,
data-informed decision making, enterprise sales partnership, mentorship, executive communication.

Education: MBA, Business Administration. BS, Computer Science.`

export const SAMPLE_JOB_DESCRIPTION = `Senior Product Manager — Enterprise Platform

We're looking for a Senior Product Manager to own our enterprise platform product line.

Requirements:
- 6+ years of product management experience, with at least 3 years in enterprise B2B SaaS.
- Proven track record owning a product roadmap and P&L.
- Experience leading cross-functional teams (engineering, design, data) without direct authority.
- Strong stakeholder management skills, including presenting to executive leadership.
- Comfortable partnering with sales and customer success on retention and expansion.

Nice to have:
- Experience with platform or infrastructure products, not just user-facing features.
- Prior people-management or formal mentorship experience.
- Background in a company operating at significant scale (50,000+ customers or similar).

We value candidates who can balance strategic thinking with hands-on execution, and who
communicate clearly with both engineers and executives.`
