/**
 * 병목 발생 시 5단계 위에 표시되는 amber 한 줄 배너.
 *
 * 시각: 직접 div (shadcn Alert 는 default/destructive 만, warning variant 없음).
 * 디자인 다듬기는 다음 "디자인 시스템 PR" 에서.
 */
import { AlertTriangle } from 'lucide-react'

import { cn } from '@/lib/utils'

type Props = {
  message: string
}

export function BottleneckBanner({ message }: Props) {
  return (
    <div
      className={cn(
        'flex items-center gap-2 rounded-md border border-amber-500',
        'bg-amber-50 px-3 py-2 text-sm text-amber-900',
        'dark:bg-amber-950/30 dark:text-amber-200',
      )}
      role='alert'
    >
      <AlertTriangle className='size-4 shrink-0' />
      <span>{message}</span>
    </div>
  )
}
