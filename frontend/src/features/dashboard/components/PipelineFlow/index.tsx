/**
 * PipelineFlow — 24h 깔때기 5단계 흐름.
 *
 * Backend: GET /api/admin/pipeline/flow (PR-2b-1)
 * Polling: 10초.
 *
 * 시각 디자인 최소 (shadcn 기본). 다음 "디자인 시스템 PR" 에서 일괄 재작성.
 *
 * 클릭 가능 카드: market_fit → /targets, task_created → /tasks
 * 나머지 정적 (PR-5 영상 통합 보기 후 추가 예정).
 */
import { useQuery } from '@tanstack/react-query'

import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { fetchApi } from '@/lib/api'

import { BottleneckBanner } from './BottleneckBanner'
import { StageCard } from './StageCard'
import type { PipelineFlowResponse } from './types'

const POLL_INTERVAL_MS = 10_000

async function fetchPipelineFlow(
  windowHours: number,
): Promise<PipelineFlowResponse> {
  return fetchApi<PipelineFlowResponse>(
    `/api/admin/pipeline/flow?window_hours=${windowHours}`,
  )
}

type Props = {
  windowHours?: number
}

export function PipelineFlow({ windowHours = 24 }: Props) {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['pipeline-flow', windowHours],
    queryFn: () => fetchPipelineFlow(windowHours),
    refetchInterval: POLL_INTERVAL_MS,
  })

  if (isLoading) {
    return <PipelineFlowSkeleton />
  }

  if (isError) {
    return (
      <Card>
        <CardContent className='p-4 text-sm text-muted-foreground'>
          파이프라인 흐름을 불러오지 못했어요.
          {error instanceof Error && error.message && (
            <span className='ml-1 text-xs'>({error.message})</span>
          )}
        </CardContent>
      </Card>
    )
  }

  if (!data || data.stages.length === 0) {
    return null
  }

  const allZero = data.stages.every((s) => s.count === 0)
  if (allZero) {
    return (
      <Card>
        <CardContent className='p-4 text-sm text-muted-foreground'>
          최근 {data.window_hours}시간 동안 활동이 없어요.
        </CardContent>
      </Card>
    )
  }

  return (
    <div className='space-y-2'>
      {data.bottleneck_message && (
        <BottleneckBanner message={data.bottleneck_message} />
      )}
      <div className='grid grid-cols-2 gap-2 md:grid-cols-5'>
        {data.stages.map((metric) => (
          <StageCard key={metric.stage} metric={metric} />
        ))}
      </div>
    </div>
  )
}

function PipelineFlowSkeleton() {
  return (
    <div className='grid grid-cols-2 gap-2 md:grid-cols-5'>
      {Array.from({ length: 5 }).map((_, i) => (
        <Card key={i}>
          <CardContent className='p-4'>
            <Skeleton className='h-3 w-12' />
            <Skeleton className='mt-2 h-7 w-10' />
            <Skeleton className='mt-2 h-3 w-16' />
          </CardContent>
        </Card>
      ))}
    </div>
  )
}
