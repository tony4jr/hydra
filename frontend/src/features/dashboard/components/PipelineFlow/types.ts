/**
 * PipelineFlow 응답 타입.
 *
 * Backend: GET /api/admin/pipeline/flow (PR-2b-1)
 * 응답 schema 는 hydra/services/dashboard_metrics.py 의 Pydantic 모델과 1:1 매칭.
 *
 * Zod 미도입 — backend Pydantic 이 schema 보장.
 */

export type StageName =
  | 'discovered'
  | 'market_fit'
  | 'task_created'
  | 'comment_posted'
  | 'survived_24h'

export interface PipelineStageMetric {
  stage: StageName
  count: number
  pass_rate: number | null  // 0~1, null = 첫 stage 또는 표본 부족
  is_bottleneck: boolean
}

export interface PipelineFlowResponse {
  window_hours: number
  stages: PipelineStageMetric[]
  bottleneck_message: string | null
  generated_at: string  // ISO datetime
}
