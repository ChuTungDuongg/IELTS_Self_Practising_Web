"use client";

import type { CSSProperties } from "react";
import { GlobalHeaderPreview } from "@/components/ui/global-header";
import { ArrowIcon, ForwardFiveIcon, RewindFiveIcon, SettingsIcon } from "@/components/ui/icons";
import { useTranslation } from "@/lib/i18n/locale-provider";
import { questionRegistry } from "@/features/questions/registry";
import { groupQuestionRange } from "@/features/questions/numbering";
import { QuestionGroupInstruction } from "@/features/questions/question-group-instruction";
import type { ExamGroup } from "@/features/questions/types";
import { ReadingPaneLayout } from "@/features/practice/reading-pane-layout";
import { PracticeBottomNavigation } from "@/features/practice/practice-bottom-navigation";
import { PracticeTools } from "@/features/practice/practice-tools";
import practiceStyles from "@/features/practice/practice-runner.module.css";
import type { AttemptPresentationMode } from "./attempt-presentation";
import { PreviewViewport } from "./preview-viewport";
import seed from "./presentation-preview-seed.json";
import styles from "./presentation-choice.module.css";

export type PresentationPreview = {
  title?: string;
  unitTitle?: string | null;
  questionTypes?: string[];
  startNumber?: number;
  questionCount?: number;
};

const readingGroups = seed.groups as ExamGroup[];
const listeningGroups: ExamGroup[] = [{ ...readingGroups[1], questions: readingGroups[1].questions.map((question, index) => ({ ...question, number: index + 1 })) }];
const values = { [readingGroups[0].questions[0].id]: "TRUE" };

/** Fictional seed content uses the canonical controls, without an attempt, controller, timer or media request. */
export function PresentationThumbnail({ mode, module, preview }: {
  mode: AttemptPresentationMode;
  module: "READING" | "LISTENING";
  preview?: PresentationPreview;
}) {
  const { t } = useTranslation();
  const practice = mode === "PRACTICE";
  const reading = module === "READING";
  const groups = reading ? readingGroups : listeningGroups;
  const questions = groups.flatMap(group => group.questions);
  const title = preview?.title || t(reading ? "common.reading" : "common.listening");
  const unitLabel = t(reading ? "common.passageNumber" : "common.sectionNumber", { number: 1 });
  const chips = questions.map((question, index) => <div key={question.id} className={`exam-question-chip ${index === 0 ? "answered current" : "unanswered"}`}>
    <button type="button" className="exam-question-number">{question.number}</button>
    {reading || !practice ? <button type="button" className="exam-question-flag">⚐</button> : null}
  </div>);
  const submit = <button type="button" className="exam-submit">{t("runner.submitAnswers")}</button>;
  const arrows = <div className="listening-sequential-navigation"><button type="button"><ArrowIcon className="listening-previous-icon" width={18} height={18} /></button><button type="button"><ArrowIcon width={18} height={18} /></button></div>;
  const timer = <span className="exam-timer">59:42</span>;
  const close = <button type="button" className="exam-pause-button">{practice ? <svg width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"><path d="m6 6 12 12M6 18 18 6" /></svg> : t("runner.pauseExit")}</button>;
  const questionContent = <>{groups.map(group => {
    const Renderer = questionRegistry[group.question_type].ExamRenderer;
    return <section key={group.id} className="exam-question-group"><h3 className={practice ? practiceStyles.groupHeading : styles.previewGroupTitle}>{groupQuestionRange(group).replace(/^Q/, `${t("common.questions")} `)}</h3><QuestionGroupInstruction group={group} passageNumber={reading ? 1 : undefined} /><Renderer group={group} values={reading ? values : {}} onAnswer={() => undefined} /></section>;
  })}</>;
  const navigation = <aside className="listening-navigation-rail"><PracticeBottomNavigation presentation={mode}><div className="listening-navigation-scroll">
    {!practice ? <nav className="listening-section-navigation"><button type="button" className="active">{unitLabel}</button></nav> : null}
    <nav className="listening-question-navigation"><div className="listening-navigation-section is-active">{practice ? <button type="button" className="practice-section-select">{unitLabel}</button> : <p>{unitLabel}</p>}<div className="listening-section-questions">{chips}</div></div></nav>
  </div><div className="listening-navigation-actions">{practice ? <button type="button" className="practice-active-flag">⚐</button> : null}{arrows}{submit}</div></PracticeBottomNavigation></aside>;
  return <PreviewViewport title={`${t(mode === "PRACTICE" ? "presentation.practice" : "presentation.exam")} · ${t(reading ? "common.reading" : "common.listening")}`}>
    <div className={styles.previewApplication} data-preview-content="fictional"><GlobalHeaderPreview />
      <div className={`${styles.runner} exam-runner ${reading ? "reading-exam" : "listening-exam listening-attempt"} ${practice ? practiceStyles.root : ""}`} data-presentation={mode} data-preview-module={module} data-reading-pane="passage">
        {!reading && practice ? <header className={practiceStyles.listeningHeader}><div className={practiceStyles.listeningIdentity}>{close}<h1>{t("common.listening")} · {title}</h1></div><div className={practiceStyles.listeningTimer}>{timer}</div><div className={practiceStyles.listeningHeaderActions}><span className="exam-save-state">{t("common.saved")}</span><span className={styles.previewSettings}><SettingsIcon width={18} height={18} />{t("practiceUi.settings")}</span></div></header>
          : <header className="exam-header"><div><p>{t(reading ? "common.reading" : "common.listening")} · {unitLabel}</p><h1>{title}</h1></div><div className="exam-header-tools">{close}<div className="exam-highlight-toolbar">{t("runner.highlightsCount", { count: 1 })}</div><div className="exam-header-status">{timer}<span className="exam-save-state">{t("common.saved")}</span></div></div></header>}
        {reading ? <ReadingPaneLayout id={`preview-${mode}`} presentation={mode}>
          <article className="exam-passage"><div className="exam-passage-content"><p className="exam-passage-kicker">{unitLabel}</p><h2>{seed.title}</h2><div className="exam-passage-body">{seed.paragraphs.map(paragraph => <p className="exam-passage-paragraph reading-passage-paragraph" key={paragraph.label}><b>{paragraph.label}</b><span className="reading-passage-text">{paragraph.text}</span></p>)}</div></div></article>
          <div className="exam-questions"><div className="exam-question-panel-heading"><p>{unitLabel}</p><h2>{t("common.questions")}</h2></div>{questionContent}</div>
        </ReadingPaneLayout> : <div className="listening-attempt-body">{practice ? <div className={practiceStyles.listeningTools}><PracticeTools mode="highlight" /></div> : null}<main className="listening-question-pane"><h2 className={practiceStyles.listeningSectionTitle}>{seed.title}</h2>{questionContent}</main>{!practice ? navigation : null}</div>}
        {!reading ? <div className="listening-audio-dock"><div className="listening-player listening-player-exam-bar" style={{ "--player-progress": "12%", "--player-volume": "70%" } as CSSProperties}>
          <div className="player-progress-row"><input type="range" aria-label={t("runner.audioSeek")} defaultValue={12} /></div><div className="player-control-row"><div className="player-left-controls"><div className="player-time-pair">03:12 / 26:40</div><div className="player-volume-controls"><button type="button" className="player-mute"><svg width={17} height={17} viewBox="0 0 24 24" fill="currentColor"><path d="m11 5-6 4H2v6h3l6 4Z" /></svg></button><input type="range" aria-label={t("runner.volume")} defaultValue={70} /></div></div><div className="player-transport"><button type="button" className="player-skip"><RewindFiveIcon width={24} height={24} /></button><button type="button" className="player-main"><svg width={21} height={21} viewBox="0 0 24 24" fill="currentColor"><path d="M8 4.5a2 2 0 0 1 3-1.7l10 7.5a2.1 2.1 0 0 1 0 3.4l-10 7.5A2 2 0 0 1 8 19.5Z" transform="translate(-2 0)" /></svg></button><button type="button" className="player-skip"><ForwardFiveIcon width={24} height={24} /></button></div><label className="player-speed-control"><span>{t("runner.speedLabel")}:</span><select aria-label={t("runner.speed")} defaultValue="1"><option value="1">1x</option></select></label></div>
        </div></div> : null}
        {reading ? <footer className="exam-footer reading-exam-footer"><PracticeBottomNavigation presentation={mode}><div className="exam-footer-navigation"><nav className="exam-passage-navigation">{[1, 2, 3].map(number => <button type="button" key={number} className={number === 1 ? "active" : ""}>{t("common.passageNumber", { number })}</button>)}</nav><nav className="exam-question-strip">{chips}</nav></div>{submit}</PracticeBottomNavigation></footer> : practice ? navigation : null}
      </div>
    </div>
  </PreviewViewport>;
}
