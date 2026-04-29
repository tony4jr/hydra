/**
 * PipelineFlow pure functions.
 *
 * UI 무관한 로직만. 단위 테스트 가능 (logic.test.ts).
 */

import type { StageName } from './types'

/** stage 의 한국어 라벨. */
export function getStageLabel(stage: StageName): string {
  const map: Record<StageName, string> = {
    discovered: '발견',
    market_fit: '시장 적합도',
    task_created: '작업 생성',
    comment_posted: '댓글 작성',
    survived_24h: '24시간 생존',
  }
  return map[stage]
}

/** stage 클릭 시 이동할 경로. null = 클릭 불가. */
export function getStageRouteTo(stage: StageName): string | null {
  const map: Record<StageName, string | null> = {
    discovered: null,
    market_fit: '/targets',
    task_created: '/tasks',
    comment_posted: null,  // PR-5 영상 통합 보기에서 추가 예정
    survived_24h: null,
  }
  return map[stage]
}

/** 클릭 가능한 stage 인지. */
export function isClickableStage(stage: StageName): boolean {
  return getStageRouteTo(stage) !== null
}

/** pass_rate (0~1) → "82%" 형식. null → null. */
export function formatPassRate(rate: number | null): string | null {
  if (rate === null) return null
  return `${Math.round(rate * 100)}%`
}
