/**
 * 5탭 placeholder. PR-4a 는 골격만, 콘텐츠는 후속 sub-PR 에서 채움.
 */
interface Props {
  tabName: string
  subPrId: string
}

export function TabPlaceholder({ tabName, subPrId }: Props) {
  return (
    <div className='bg-card border border-dashed border-border rounded-xl py-16 text-center'>
      <p className='text-foreground text-[15px] font-medium mb-1'>{tabName}</p>
      <p className='text-muted-foreground/70 text-[12px]'>준비 중 ({subPrId})</p>
    </div>
  )
}
