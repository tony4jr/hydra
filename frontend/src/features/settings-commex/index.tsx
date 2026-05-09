import { useState } from 'react'
import { Save } from 'lucide-react'
import { toast } from 'sonner'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { ThemeSwitch } from '@/components/theme-switch'

export function SettingsCommex() {
  const [model, setModel] = useState('gpt-4.1')
  const [limit, setLimit] = useState('500')
  const [channel, setChannel] = useState('Slack')
  const [yt, setYt] = useState('••••••••••••••••')
  const [ai, setAi] = useState('••••••••••••••••')
  const [memo, setMemo] = useState(
    '초안 생성과 게시 한도를 분리해서 관리합니다.'
  )
  const [dryRun, setDryRun] = useState(false)

  const save = () => {
    toast.success('전역 설정이 저장됐어요', {
      description: `모델: ${model} · 일일 한도: ${limit} · 알림: ${channel}`,
    })
  }

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
              <h1 className='cx-page-h'>전역 설정</h1>
              <p className='cx-page-sub'>
                API 키, 기본 모델, 한도와 알림 정책을 설정합니다.
              </p>
            </div>
            <button className='cx-btn-primary' onClick={save}>
              <Save className='inline h-4 w-4 mr-1.5' />저장
            </button>
          </div>

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: '1fr 1fr',
              gap: 18,
            }}
            className='cx-settings-grid'
          >
            {/* 운영 정책 */}
            <div className='cx-card cx-card-pad'>
              <div className='cx-section-head'>
                <div className='cx-section-title'>운영 정책</div>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                <Field label='기본 모델' help='댓글 생성에 기본으로 사용되는 모델'>
                  <select
                    className='cx-input'
                    value={model}
                    onChange={(e) => setModel(e.target.value)}
                  >
                    <option>gpt-4.1</option>
                    <option>gpt-4o</option>
                    <option>claude-3.5-sonnet</option>
                  </select>
                </Field>
                <Field label='일일 기본 한도 (계정당)' help='과부하 / 차단 방지용'>
                  <input
                    className='cx-input'
                    value={limit}
                    onChange={(e) => setLimit(e.target.value)}
                    type='number'
                  />
                </Field>
                <Field label='알림 채널' help='실패·경고·이슈 알림 수신처'>
                  <select
                    className='cx-input'
                    value={channel}
                    onChange={(e) => setChannel(e.target.value)}
                  >
                    <option>Slack</option>
                    <option>Email</option>
                    <option>Webhook</option>
                  </select>
                </Field>
                <Toggle
                  label='Dry-run 모드'
                  desc='실제 게시 대신 로그만 남깁니다 (테스트용)'
                  on={dryRun}
                  onChange={setDryRun}
                />
              </div>
            </div>

            {/* API 키 + 시스템 메모 */}
            <div className='cx-card cx-card-pad'>
              <div className='cx-section-head'>
                <div className='cx-section-title'>API 연동</div>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                <Field
                  label='YouTube API Key'
                  help='영상 메타·댓글 수집에 사용'
                >
                  <input
                    className='cx-input'
                    value={yt}
                    onChange={(e) => setYt(e.target.value)}
                    type='password'
                  />
                </Field>
                <Field
                  label='OpenAI API Key'
                  help='기본 모델 호출에 사용'
                >
                  <input
                    className='cx-input'
                    value={ai}
                    onChange={(e) => setAi(e.target.value)}
                    type='password'
                  />
                </Field>
                <Field label='시스템 메모'>
                  <textarea
                    className='cx-input'
                    style={{ minHeight: 100, resize: 'vertical', lineHeight: 1.5 }}
                    value={memo}
                    onChange={(e) => setMemo(e.target.value)}
                  />
                </Field>
              </div>
            </div>
          </div>
        </div>
      </Main>
    </>
  )
}

function Field({
  label,
  help,
  children,
}: {
  label: string
  help?: string
  children: React.ReactNode
}) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <label style={{ fontSize: 13, fontWeight: 800, color: '#44506a' }}>{label}</label>
      {children}
      {help && (
        <span style={{ fontSize: 11, color: 'var(--cx-sub)' }}>{help}</span>
      )}
    </div>
  )
}

function Toggle({
  label,
  desc,
  on,
  onChange,
}: {
  label: string
  desc: string
  on: boolean
  onChange: (v: boolean) => void
}) {
  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        padding: 12,
        borderRadius: 12,
        background: '#fbfcff',
        border: '1px solid var(--cx-line-2)',
      }}
    >
      <div>
        <div style={{ fontSize: 13, fontWeight: 800, color: 'var(--cx-text)' }}>{label}</div>
        <div style={{ fontSize: 11, color: 'var(--cx-sub)', marginTop: 2 }}>{desc}</div>
      </div>
      <button
        onClick={() => onChange(!on)}
        style={{
          width: 44,
          height: 26,
          borderRadius: 999,
          border: 'none',
          cursor: 'pointer',
          position: 'relative',
          background: on ? 'linear-gradient(135deg,#5e74ff,#6d5cff)' : '#d7dff1',
        }}
        aria-pressed={on}
      >
        <span
          style={{
            position: 'absolute',
            top: 3,
            left: on ? 21 : 3,
            width: 20,
            height: 20,
            borderRadius: '50%',
            background: '#fff',
            boxShadow: '0 2px 6px rgba(0,0,0,0.15)',
            transition: 'left 0.18s ease',
          }}
        />
      </button>
    </div>
  )
}

export default SettingsCommex
