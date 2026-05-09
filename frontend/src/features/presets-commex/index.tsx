import { Plus, Eye, Puzzle } from 'lucide-react'
import { toast } from 'sonner'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { ThemeSwitch } from '@/components/theme-switch'
import { GLOBAL_PRESETS } from '../_commex-mock'

export function PresetsCommex() {
  const tones = ['cx-bg-purple', 'cx-bg-blue', 'cx-bg-green', 'cx-bg-orange'] as const
  return (
    <>
      <Header fixed>
        <div className='ml-auto flex items-center space-x-4'>
          <ThemeSwitch />
          <ProfileDropdown />
        </div>
      </Header>
      <Main>
        <div
          className='hydra-page'
          style={{ display: 'flex', flexDirection: 'column', gap: 18 }}
        >
          <div className='flex items-end justify-between flex-wrap gap-3'>
            <div>
              <h1 className='cx-page-h'>글로벌 프리셋</h1>
              <p className='cx-page-sub'>
                여러 브랜드/니치에서 재사용할 수 있는 기본 프리셋 라이브러리입니다.
              </p>
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button className='cx-btn-soft' onClick={() => toast.info('미리보기 (준비중)')}>
                <Eye className='inline h-4 w-4 mr-1.5' />미리보기
              </button>
              <button className='cx-btn-primary' onClick={() => toast.success('새 프리셋 만들기 (예정)')}>
                <Plus className='inline h-4 w-4 mr-1' />새 프리셋
              </button>
            </div>
          </div>

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
              gap: 14,
            }}
          >
            {GLOBAL_PRESETS.map((p, i) => (
              <div
                key={p.id}
                className='cx-card cx-card-pad cx-card-hover'
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 10,
                  cursor: 'pointer',
                }}
                onClick={() => toast.info(`${p.name} 슬롯 편집 (다음 단계)`)}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span
                    className={`cx-kpi-circle ${tones[i % 4]}`}
                    style={{ width: 40, height: 40 }}
                  >
                    <Puzzle className='h-4 w-4' />
                  </span>
                  <span style={{ fontSize: 11, color: 'var(--cx-sub)', fontWeight: 800 }}>
                    {p.version}
                  </span>
                </div>
                <h4
                  style={{
                    margin: 0,
                    fontSize: 16,
                    fontWeight: 800,
                    color: 'var(--cx-text)',
                  }}
                >
                  {p.name}
                </h4>
                <p
                  style={{
                    margin: 0,
                    fontSize: 13,
                    color: 'var(--cx-sub)',
                    lineHeight: 1.5,
                    flex: 1,
                  }}
                >
                  {p.desc}
                </p>
                <div
                  style={{
                    fontSize: 12,
                    color: 'var(--cx-primary)',
                    fontWeight: 800,
                    paddingTop: 8,
                    borderTop: '1px solid var(--cx-line-2)',
                  }}
                >
                  {p.used.toLocaleString()} 회 사용
                </div>
              </div>
            ))}
          </div>
        </div>
      </Main>
    </>
  )
}

export default PresetsCommex
