import { useEffect, useState } from 'react'
import { Eye, EyeOff, Save, Send } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Separator } from '@/components/ui/separator'
import { ContentSection } from '../components/content-section'
import { fetchApi } from '@/lib/api'
import { toast } from 'sonner'

interface ApiSettings {
  claude_api_key?: string
  youtube_api_key?: string
  captcha_api_key?: string
  telegram_bot_token?: string
  telegram_chat_id?: string
  server_host?: string
  server_port?: string
}

function MaskedInput({ id, value, onChange, placeholder }: {
  id: string; value: string; onChange: (v: string) => void; placeholder?: string
}) {
  const [visible, setVisible] = useState(false)
  return (
    <div className='relative'>
      <Input
        id={id}
        type={visible ? 'text' : 'password'}
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        className='pr-10'
      />
      <Button
        type='button'
        variant='ghost'
        size='icon'
        className='absolute top-0 right-0 h-full'
        onClick={() => setVisible(!visible)}
      >
        {visible ? <EyeOff className='h-4 w-4' /> : <Eye className='h-4 w-4' />}
      </Button>
    </div>
  )
}

export function SettingsGeneral() {
  const [settings, setSettings] = useState<ApiSettings>({})
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)

  useEffect(() => {
    fetchApi<{ settings: ApiSettings }>('/settings/api/all')
      .then(data => setSettings(data.settings || {}))
      .catch(() => {})
  }, [])

  const update = (key: keyof ApiSettings, value: string) => {
    setSettings(prev => ({ ...prev, [key]: value }))
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      const result = await fetchApi<{ ok: boolean; saved: number }>(
        '/settings/api/save',
        { method: 'POST', body: JSON.stringify(settings) },
      )
      toast.success('저장됨', {
        description: `${result?.saved ?? Object.keys(settings).length}개 항목 저장됨`,
      })
    } catch (e) {
      toast.error('저장 실패', {
        description: e instanceof Error ? e.message : String(e),
      })
    } finally {
      setSaving(false)
    }
  }

  const handleTestTelegram = async () => {
    setTesting(true)
    try {
      await fetchApi('/settings/api/test-telegram', { method: 'POST' })
      toast.success('Telegram 테스트 메시지 전송')
    } catch (e) {
      toast.error('전송 실패', {
        description: e instanceof Error ? e.message : String(e),
      })
    } finally {
      setTesting(false)
    }
  }

  return (
    <ContentSection title='일반' desc='서버 정보, API 키, 알림 설정을 관리합니다.'>
      <div className='space-y-6'>
        {/* Server */}
        <div>
          <h4 className='text-foreground font-semibold text-[14px] mb-3'>서버 정보</h4>
          <div className='grid grid-cols-2 gap-4'>
            <div className='mb-5'>
              <label className='text-foreground text-sm font-medium mb-1.5'>호스트</label>
              <Input value={settings.server_host || 'localhost'} readOnly className='bg-muted' />
            </div>
            <div className='mb-5'>
              <label className='text-foreground text-sm font-medium mb-1.5'>포트</label>
              <Input value={settings.server_port || '8000'} readOnly className='bg-muted' />
            </div>
          </div>
        </div>

        <Separator />

        {/* API Keys */}
        <div>
          <h4 className='text-foreground font-semibold text-[14px] mb-3'>API 키</h4>
          <div className='space-y-4'>
            <div className='mb-5'>
              <label className='text-foreground text-sm font-medium mb-1.5'>Claude API Key</label>
              <p className='text-muted-foreground text-xs mb-2'>AI 댓글 생성에 사용되는 Anthropic API 키</p>
              <MaskedInput id='claude-key' value={settings.claude_api_key || ''} onChange={v => update('claude_api_key', v)} placeholder='sk-ant-...' />
            </div>
            <div className='mb-5'>
              <label className='text-foreground text-sm font-medium mb-1.5'>YouTube API Key</label>
              <p className='text-muted-foreground text-xs mb-2'>영상 검색 및 수집에 사용되는 YouTube Data API 키</p>
              <MaskedInput id='youtube-key' value={settings.youtube_api_key || ''} onChange={v => update('youtube_api_key', v)} placeholder='AIza...' />
            </div>
            <div className='mb-5'>
              <label className='text-foreground text-sm font-medium mb-1.5'>2Captcha API Key</label>
              <p className='text-muted-foreground text-xs mb-2'>캡챠 자동 풀이에 사용되는 2Captcha API 키</p>
              <MaskedInput id='captcha-key' value={settings.captcha_api_key || ''} onChange={v => update('captcha_api_key', v)} />
            </div>
          </div>
        </div>

        <Separator />

        {/* Telegram */}
        <div>
          <h4 className='text-foreground font-semibold text-[14px] mb-3'>텔레그램 알림</h4>
          <div className='space-y-4'>
            <div className='mb-5'>
              <label className='text-foreground text-sm font-medium mb-1.5'>Bot Token</label>
              <p className='text-muted-foreground text-xs mb-2'>@BotFather에서 발급받은 토큰</p>
              <MaskedInput id='tg-token' value={settings.telegram_bot_token || ''} onChange={v => update('telegram_bot_token', v)} />
            </div>
            <div className='mb-5'>
              <label className='text-foreground text-sm font-medium mb-1.5'>Chat ID</label>
              <p className='text-muted-foreground text-xs mb-2'>알림을 받을 채팅방 ID</p>
              <MaskedInput id='tg-chat' value={settings.telegram_chat_id || ''} onChange={v => update('telegram_chat_id', v)} />
            </div>
            <Button variant='outline' size='sm' onClick={handleTestTelegram} disabled={testing} className='hydra-btn-press'>
              <Send className='mr-2 h-4 w-4' />
              {testing ? '전송 중...' : '테스트 전송'}
            </Button>
          </div>
        </div>

        <Separator />

        <div className='flex justify-end'>
          <Button onClick={handleSave} disabled={saving} className='hydra-btn-press'>
            <Save className='mr-2 h-4 w-4' />
            {saving ? '저장 중...' : '저장'}
          </Button>
        </div>
      </div>
    </ContentSection>
  )
}
