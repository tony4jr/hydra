import { ContentSection } from '../components/content-section'
import { DisplayForm } from './display-form'

export function SettingsDisplay() {
  return (
    <ContentSection
      title='화면'
      desc='어드민 패널에 표시할 항목을 켜고 끕니다.'
    >
      <DisplayForm />
    </ContentSection>
  )
}
