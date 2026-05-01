/**
 * 수집 탭 (PR-4c). spec PR-4 §2.
 *
 * 5단계 깔때기 + 키워드 + 최근 영상.
 * 임계값 시뮬레이터는 후속 sub-PR (옵션, spec).
 */
import {
  useCollectionFlow,
  useNicheKeywords,
  useRecentVideos,
} from '@/hooks/use-collection'
import type { FlowStage, KeywordPolling } from '@/types/niche'
import { Skeleton } from '@/components/ui/skeleton'

const STAGE_LABEL: Record<FlowStage['stage'], string> = {
  discovered: '발견',
  market_fit: '시장 적합',
  in_pool: '풀 진입',
  comment_posted: '댓글 작성',
}

interface Props {
  nicheId: string
}

export function CollectionTab({ nicheId }: Props) {
  return (
    <div className='space-y-5'>
      <FlowSection nicheId={nicheId} />
      <KeywordsSection nicheId={nicheId} />
      <RecentVideosSection nicheId={nicheId} />
    </div>
  )
}

function FlowSection({ nicheId }: { nicheId: string }) {
  const { flow, loading } = useCollectionFlow(nicheId, 24)
  if (loading) {
    return (
      <div className='grid gap-3 grid-cols-2 md:grid-cols-4'>
        {[1, 2, 3, 4].map((i) => (
          <Skeleton key={i} className='h-20 rounded-xl' />
        ))}
      </div>
    )
  }
  if (!flow) {
    return (
      <div className='bg-card border border-border rounded-xl py-8 text-center'>
        <p className='text-muted-foreground text-[13px]'>흐름을 불러오지 못했어요</p>
      </div>
    )
  }
  return (
    <div>
      <p className='text-muted-foreground text-[12px] mb-2'>
        24시간 수집 흐름 · 임계값 {flow.threshold}
      </p>
      <div className='grid gap-3 grid-cols-2 md:grid-cols-4'>
        {flow.stages.map((s) => (
          <div
            key={s.stage}
            className={
              'bg-card border rounded-xl p-4 ' +
              (s.is_bottleneck ? 'border-rose-400/60' : 'border-border')
            }
          >
            <p className='text-muted-foreground text-[12px]'>{STAGE_LABEL[s.stage]}</p>
            <p className='text-foreground font-semibold mt-1 text-[32px] leading-none'>
              {s.count}
            </p>
            {s.pass_rate !== null && (
              <p className='text-muted-foreground/70 text-[11px] mt-1'>
                통과율 {(s.pass_rate * 100).toFixed(0)}%
                {s.is_bottleneck && <span className='text-rose-500 ml-1'>· 병목</span>}
              </p>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

function KeywordsSection({ nicheId }: { nicheId: string }) {
  const { keywords, loading, updatePolling } = useNicheKeywords(nicheId)
  if (loading) {
    return <Skeleton className='h-40 rounded-xl' />
  }
  return (
    <div className='bg-card border border-border rounded-xl p-5'>
      <p className='text-muted-foreground text-[12px] mb-3'>
        활성 키워드 ({keywords.length})
      </p>
      {keywords.length === 0 ? (
        <p className='text-muted-foreground/60 text-[13px]'>등록된 키워드가 없어요</p>
      ) : (
        <ul className='divide-y divide-border'>
          {keywords.map((kw) => (
            <li key={kw.id} className='py-3 flex items-center justify-between gap-3'>
              <div className='min-w-0'>
                <p className='text-foreground text-[14px] font-medium truncate'>
                  {kw.text}
                  {kw.kind === 'negative' && (
                    <span className='hydra-tag hydra-tag-muted ml-2'>부정</span>
                  )}
                </p>
                <p className='text-muted-foreground/70 text-[11px] mt-0.5'>
                  발견 {kw.metrics_7d.discovered} · 통과 {kw.metrics_7d.passed_market}
                  {kw.metrics_7d.pass_rate !== null && (
                    <> · 통과율 {(kw.metrics_7d.pass_rate * 100).toFixed(0)}%</>
                  )}
                  {kw.variations.length > 0 && <> · 변형 {kw.variations.length}</>}
                </p>
              </div>
              <select
                value={kw.polling}
                onChange={(e) =>
                  updatePolling(kw.id, e.target.value as KeywordPolling)
                }
                className='bg-background border border-border rounded-md text-[12px] px-2 py-1'
              >
                <option value='5min'>5분</option>
                <option value='30min'>30분</option>
                <option value='daily'>일일</option>
              </select>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

const RESULT_LABEL: Record<string, { label: string; tone: string }> = {
  passed: { label: '통과', tone: 'hydra-tag-primary' },
  rejected_market: { label: '시장 탈락', tone: 'hydra-tag-muted' },
  rejected_hard_block: { label: '강제 제외', tone: 'hydra-tag-muted' },
  rejected_other: { label: '기타', tone: 'hydra-tag-muted' },
}

function RecentVideosSection({ nicheId }: { nicheId: string }) {
  const { videos, loading } = useRecentVideos(nicheId, 30)
  if (loading) {
    return <Skeleton className='h-48 rounded-xl' />
  }
  return (
    <div className='bg-card border border-border rounded-xl p-5'>
      <p className='text-muted-foreground text-[12px] mb-3'>
        최근 발견 영상 ({videos.length})
      </p>
      {videos.length === 0 ? (
        <p className='text-muted-foreground/60 text-[13px]'>최근 발견된 영상이 없어요</p>
      ) : (
        <ul className='divide-y divide-border'>
          {videos.map((v) => {
            const meta = RESULT_LABEL[v.result] ?? RESULT_LABEL.rejected_other
            return (
              <li key={v.video_id} className='py-2.5 flex items-center justify-between gap-3'>
                <div className='min-w-0'>
                  <a
                    href={v.url}
                    target='_blank'
                    rel='noreferrer'
                    className='text-foreground text-[13px] font-medium truncate block hover:underline'
                  >
                    {v.title || v.video_id}
                  </a>
                  <p className='text-muted-foreground/70 text-[11px] mt-0.5'>
                    {v.channel || '채널 정보 없음'}
                    {v.view_count !== null && <> · {v.view_count.toLocaleString()}회</>}
                    {v.market_fitness !== null && (
                      <> · 적합도 {v.market_fitness.toFixed(2)}</>
                    )}
                  </p>
                </div>
                <span className={`hydra-tag ${meta.tone}`}>
                  {meta.label}
                  {v.result_reason && (
                    <span className='ml-1 opacity-70'>· {v.result_reason}</span>
                  )}
                </span>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
