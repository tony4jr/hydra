import { describe, it, expect } from 'vitest'
import {
  getStageLabel,
  getStageRouteTo,
  isClickableStage,
  formatPassRate,
} from './logic'

describe('getStageLabel', () => {
  it('returns Korean label for each stage', () => {
    expect(getStageLabel('discovered')).toBe('발견')
    expect(getStageLabel('market_fit')).toBe('시장 적합도')
    expect(getStageLabel('task_created')).toBe('작업 생성')
    expect(getStageLabel('comment_posted')).toBe('댓글 작성')
    expect(getStageLabel('survived_24h')).toBe('24시간 생존')
  })
})

describe('getStageRouteTo', () => {
  it('returns route for clickable stages', () => {
    expect(getStageRouteTo('market_fit')).toBe('/targets')
    expect(getStageRouteTo('task_created')).toBe('/tasks')
  })

  it('returns null for non-clickable stages', () => {
    expect(getStageRouteTo('discovered')).toBeNull()
    expect(getStageRouteTo('comment_posted')).toBeNull()
    expect(getStageRouteTo('survived_24h')).toBeNull()
  })
})

describe('isClickableStage', () => {
  it('returns true for stages with route', () => {
    expect(isClickableStage('market_fit')).toBe(true)
    expect(isClickableStage('task_created')).toBe(true)
  })

  it('returns false for stages without route', () => {
    expect(isClickableStage('discovered')).toBe(false)
    expect(isClickableStage('comment_posted')).toBe(false)
    expect(isClickableStage('survived_24h')).toBe(false)
  })
})

describe('formatPassRate', () => {
  it('formats decimal as percentage', () => {
    expect(formatPassRate(0.82)).toBe('82%')
    expect(formatPassRate(0.05)).toBe('5%')
    expect(formatPassRate(1.0)).toBe('100%')
  })

  it('rounds to nearest integer', () => {
    expect(formatPassRate(0.825)).toBe('83%')  // Math.round(82.5) → 83
    expect(formatPassRate(0.123)).toBe('12%')
  })

  it('returns null for null input', () => {
    expect(formatPassRate(null)).toBeNull()
  })

  it('handles 0', () => {
    expect(formatPassRate(0)).toBe('0%')
  })
})
