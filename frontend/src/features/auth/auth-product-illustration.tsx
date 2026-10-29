import { AppLogo } from "@/components/ui/app-logo";
import { UiText } from "@/lib/i18n/locale-provider";
import { AuthIcon } from "./auth-icons";
import styles from "./auth.module.css";

const skills = [
  { name: "reading", message: "common.reading" },
  { name: "listening", message: "common.listening" },
  { name: "writing", message: "common.writing" },
  { name: "speaking", message: "common.speaking" },
] as const;

// An abstract product illustration: no account data, scores, or interactive controls.
export function AuthProductIllustration() {
  return <div className={styles.illustration} aria-hidden="true">
    <div className={styles.orbit} />
    <div className={styles.orbitInner} />
    <div className={styles.device}>
      <div className={styles.screen}>
        <div className={styles.previewSidebar}>
          <AppLogo variant="primary" />
          <span className={styles.previewNavActive} /><span /><span /><span />
          <i />
        </div>
        <div className={styles.previewBody}>
          <div className={styles.previewTopbar}><strong>BandPilot</strong><span><i /><i /><i /></span></div>
          <div className={styles.previewHeading}><span><UiText message="shell.analytics" /></span><i /></div>
          <div className={styles.previewChart}>
            <svg viewBox="0 0 320 105" fill="none" preserveAspectRatio="none" focusable="false">
              <path className={styles.chartGrid} d="M0 20h320M0 52h320M0 84h320" />
              <path className={styles.chartArea} d="M0 90 25 82 52 88 82 65 110 72 142 51 168 58 195 36 225 44 252 22 280 29 320 7v98H0Z" />
              <path className={styles.chartLine} d="m0 90 25-8 27 6 30-23 28 7 32-21 26 7 27-22 30 8 27-22 28 7 40-22" />
            </svg>
          </div>
          <div className={styles.previewActivity}>
            {skills.map(skill => <div key={skill.name} data-skill={skill.name}><AuthIcon name={skill.name} /><span><i /><i /></span><b /></div>)}
          </div>
        </div>
      </div>
      <div className={styles.deviceBase}><i /></div>
    </div>
    {skills.map(skill => <div key={skill.name} className={styles.skillCard} data-skill={skill.name}>
      <span className={styles.skillIcon}><AuthIcon name={skill.name} /></span>
      <span><UiText message={skill.message} /></span>
      <div className={styles.skillDetail}><i /><i /><i /></div>
    </div>)}
  </div>;
}
