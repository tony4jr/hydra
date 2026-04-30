/**
 * 단일 stage 카드.
 *
 * 시각: shadcn Card 기반 + Tailwind 기본.
 * 디자인 다듬기는 다음 "디자인 시스템 PR" 에서.
 */
import { Link } from '@tanstack/react-router'

import { Card, CardContent } from '@/components/ui/card'
import { cn } from '@/lib/utils'

import {
  formatPassRate,
  getStageIcon,
  getStageLabel,
  getStageRouteTo,
  isClickableStage,
} from './logic'
import type { PipelineStageMetric } from './types'

type Props = {
  metric: PipelineStageMetric
}

export function StageCard({ metric }: Props) {
  const { stage, count, pass_rate, is_bottleneck } = metric
  const label = getStageLabel(stage)
  const passRateText = formatPassRate(pass_rate)
  const route = getStageRouteTo(stage)
  const clickable = isClickableStage(stage)
  const Icon = getStageIcon(stage)

  const cardClassName = cn(
    'transition-colors',
    is_bottleneck && 'border-amber-500',
    clickable && 'cursor-pointer hover:border-foreground/30',
  )

  const inner = (
    <Card className={cardClassName}>
      <CardContent className='p-4'>
        <div className='flex items-center gap-2'>
          <Icon className='size-3.5 text-muted-foreground' />
          <span className='text-muted-foreground text-xs'>{label}</span>
        </div>
        <div className='mt-2 text-3xl font-semibold tabular-nums'>{count}</div>
        <div className='mt-1 text-xs'>
          {passRateText !== null ? (
            <span
              className={cn(
                is_bottleneck ? 'text-amber-600' : 'text-muted-foreground',
              )}
            >
              통과율 {passRateText}
            </span>
          ) : (
            <span className='text-muted-foreground/50'>—</span>
          )}
        </div>
        {is_bottleneck && (
          <div className='mt-1 text-[10px] font-medium text-amber-600'>
            ⚠ 병목
          </div>
        )}
      </CardContent>
    </Card>
  )

  if (clickable && route) {
    return <Link to={route}>{inner}</Link>
  }
  return inner
}
