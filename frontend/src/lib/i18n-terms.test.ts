/**
 * i18n-terms 단위 테스트.
 *
 * PR-1 §완료정의: term() fallback 동작 확인.
 * 추가: 각 매핑 객체의 키 개수 검증 (CLAUDE.md §6 매핑표 누락 방지).
 */
import { describe, it, expect } from 'vitest'
import {
  term,
  lifecyclePhase,
  tier,
  taskState,
  accountState,
  videoState,
  priority,
  labels,
} from './i18n-terms'


describe('term() helper', () => {
  it('매핑에 있는 키는 매핑 값 반환', () => {
    expect(term(tier, 'L1')).toBe('장기 자산')
    expect(term(tier, 'L4')).toBe('롱테일')
    expect(term(lifecyclePhase, 1)).toBe('신규 영상')
    expect(term(taskState, 'pending')).toBe('대기')
  })

  it('매핑에 없는 키 + fallback 미지정 → 키 자체 반환', () => {
    expect(term(tier, 'L99')).toBe('L99')
    expect(term(taskState, 'unknown_state')).toBe('unknown_state')
    expect(term(lifecyclePhase, 999)).toBe('999')
  })

  it('매핑에 없는 키 + fallback 명시 → fallback 반환', () => {
    expect(term(tier, 'L99', '알 수 없음')).toBe('알 수 없음')
    expect(term(taskState, 'foo', '—')).toBe('—')
  })

  it('빈 문자열 fallback 도 정상 반환', () => {
    expect(term(tier, 'L99', '')).toBe('')
  })

  it('매핑에 있는 키는 fallback 무시', () => {
    // 매핑값 우선
    expect(term(tier, 'L1', 'IGNORED')).toBe('장기 자산')
  })
})


describe('매핑 객체 키 개수', () => {
  it('lifecyclePhase: 1~4 정확히 4개', () => {
    const keys = Object.keys(lifecyclePhase)
    expect(keys).toHaveLength(4)
    expect(keys.sort()).toEqual(['1', '2', '3', '4'])
  })

  it('tier: L1~L4 정확히 4개', () => {
    const keys = Object.keys(tier)
    expect(keys).toHaveLength(4)
    expect(keys.sort()).toEqual(['L1', 'L2', 'L3', 'L4'])
  })

  it('taskState: pending/in_progress/done/failed 정확히 4개', () => {
    const keys = Object.keys(taskState).sort()
    expect(keys).toEqual(['done', 'failed', 'in_progress', 'pending'])
  })

  it('accountState: 6개 상태 (active/warmup/cooldown/suspended/ghost/verifying)', () => {
    const keys = Object.keys(accountState).sort()
    expect(keys).toEqual([
      'active', 'cooldown', 'ghost', 'suspended', 'verifying', 'warmup',
    ])
  })

  it('videoState: 운영자 의도된 상태 모두 포함', () => {
    // active, pending, blocked, blacklisted (alias), paused, retired, completed
    expect(videoState.active).toBe('활성')
    expect(videoState.blocked).toBe('차단')
    expect(videoState.blacklisted).toBe('차단')  // 동일 표시
    expect(videoState.retired).toBe('은퇴')
  })

  it('priority: high/normal/low 정확히 3개', () => {
    const keys = Object.keys(priority).sort()
    expect(keys).toEqual(['high', 'low', 'normal'])
  })
})


describe('labels 객체', () => {
  it('CLAUDE.md §6 핵심 라벨 모두 존재', () => {
    expect(labels.marketDefinition).toBe('시장 정의')
    expect(labels.marketFitness).toBe('시장 적합도')
    expect(labels.autoExclusion).toBe('자동 제외')
    expect(labels.ghostDetection).toBe('댓글 생존 검증')
    expect(labels.apiQuota).toBe('API 사용량')
    expect(labels.pageWorkers).toBe('작업 PC')
  })
})
