import { ContentSection } from '../components/content-section'
import { AppearanceForm } from './appearance-form'

export function SettingsAppearance() {
  return (
    <ContentSection
      title='외관'
      desc='앱의 테마와 외관을 설정합니다.'
    >
      <AppearanceForm />
    </ContentSection>
  )
}
