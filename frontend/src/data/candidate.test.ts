import { describe, it, expect } from 'vitest'
import { toCandidate, initialsFromName } from './candidate'
import { fixtureResumeAnalysis } from '../testFixtures'
import type { ResumeAnalysisResult } from './types'

function analysisWithProfile(
  profile: ResumeAnalysisResult['candidate_profile'],
): ResumeAnalysisResult {
  return { ...fixtureResumeAnalysis, candidate_profile: profile }
}

describe('initialsFromName', () => {
  it('uses first and last initials for a multi-word name', () => {
    expect(initialsFromName('Ada Lovelace')).toBe('AL')
  })

  it('uses the single initial for a one-word name', () => {
    expect(initialsFromName('Prince')).toBe('P')
  })

  it('skips middle names rather than letting them displace the surname', () => {
    expect(initialsFromName('Ada Byron Lovelace')).toBe('AL')
  })

  it('uppercases and tolerates irregular whitespace', () => {
    expect(initialsFromName('  ada   lovelace  ')).toBe('AL')
  })

  it('returns an empty string for a blank name rather than throwing', () => {
    expect(initialsFromName('   ')).toBe('')
  })
})

describe('toCandidate', () => {
  it('converts a fully populated profile', () => {
    const candidate = toCandidate(
      analysisWithProfile({
        name: 'Ada Lovelace',
        current_company: 'Analytical Engines Ltd',
        title: 'Principal Engineer',
        years_experience: 12,
      }),
    )

    expect(candidate).toEqual({
      name: 'Ada Lovelace',
      initials: 'AL',
      title: 'Principal Engineer',
      company: 'Analytical Engines Ltd',
      yearsExperience: 12,
    })
  })

  it('passes null optional fields through rather than inventing placeholders', () => {
    const candidate = toCandidate(
      analysisWithProfile({
        name: 'Prince',
        current_company: null,
        title: null,
        years_experience: null,
      }),
    )

    expect(candidate).toEqual({
      name: 'Prince',
      initials: 'P',
      title: null,
      company: null,
      yearsExperience: null,
    })
  })

  it('preserves a zero years_experience instead of treating it as missing', () => {
    // 0 is falsy but meaningful -- a genuine new-graduate resume.
    const candidate = toCandidate(
      analysisWithProfile({
        name: 'Ada Lovelace',
        current_company: null,
        title: null,
        years_experience: 0,
      }),
    )

    expect(candidate?.yearsExperience).toBe(0)
  })

  it('returns null when the analysis carries no candidate_profile (historical record)', () => {
    expect(toCandidate(fixtureResumeAnalysis)).toBeNull()
  })

  it('returns null when candidate_profile is explicitly null', () => {
    expect(toCandidate(analysisWithProfile(null))).toBeNull()
  })

  it('returns null when there is no analysis at all', () => {
    expect(toCandidate(null)).toBeNull()
  })
})
