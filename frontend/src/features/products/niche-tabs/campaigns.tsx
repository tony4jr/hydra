/**
 * 캠페인 탭 (PR-4e). spec PR-4 §4.
 *
 * niche-scoped 캠페인 리스트 + pause/resume.
 * 신규 캠페인 생성 (2-step wizard) 은 후속 sub-PR.
 */
import { useNicheCampaigns } from '@/hooks/use-niche-campaigns'
import type { NicheCampaign } from '@/types/niche'
import { Skeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'

interface Props {
  nicheId: string
}

export function CampaignsTab({ nicheId }: Props) {
  const { campaigns, loading, pause, resume } = useNicheCampaigns(nicheId)

  if (loading) {
    return <Skeleton className='h-64 rounded-xl' />
  }

  if (campaigns.length === 0) {
    return (
      <div className='bg-card border border-border rounded-xl py-16 text-center'>
        <p className='text-muted-foreground text-[14px] mb-1'>등록된 캠페인이 없어요</p>
        <p className='text-muted-foreground/60 text-[12px]'>
          후속 sub-PR (캠페인 생성 wizard) 에서 만들 수 있어요
        </p>
      </div>
    )
  }

  return (
    <div className='bg-card border border-border rounded-xl p-5'>
      <p className='text-muted-foreground text-[12px] mb-3'>
        캠페인 ({campaigns.length})
      </p>
      <ul className='divide-y divide-border'>
        {campaigns.map((c) => (
          <CampaignRow key={c.id} c={c} onPause={pause} onResume={resume} />
        ))}
      </ul>
    </div>
  )
}

function CampaignRow({
  c,
  onPause,
  onResume,
}: {
  c: NicheCampaign
  onPause: (id: number) => Promise<void>
  onResume: (id: number) => Promise<void>
}) {
  const canPause = c.status === 'active' || c.status === 'planning'
  const canResume = c.status === 'paused'

  return (
    <li className='py-3 flex items-center justify-between gap-3'>
      <div className='min-w-0'>
        <p className='text-foreground text-[14px] font-medium truncate'>
          {c.name || `캠페인 #${c.id}`}
        </p>
        <p className='text-muted-foreground/70 text-[11px] mt-0.5'>
          {c.scenario}
          {c.target_count !== null && <> · 목표 {c.target_count}</>}
          {c.duration_days !== null && <> · {c.duration_days}일</>}
          {c.start_date && (
            <> · {new Date(c.start_date).toLocaleDateString('ko-KR')}</>
          )}
        </p>
      </div>
      <div className='flex items-center gap-2'>
        <span className={`hydra-tag ${statusTone(c.status)}`}>{c.status}</span>
        {canPause && (
          <Button variant='ghost' size='sm' onClick={() => onPause(c.id)}>
            일시정지
          </Button>
        )}
        {canResume && (
          <Button variant='ghost' size='sm' onClick={() => onResume(c.id)}>
            재개
          </Button>
        )}
      </div>
    </li>
  )
}

function statusTone(status: string): string {
  if (status === 'active') return 'hydra-tag-primary'
  if (status === 'paused') return 'hydra-tag-muted'
  if (status === 'completed') return 'hydra-tag-muted'
  return 'hydra-tag-muted'
}
