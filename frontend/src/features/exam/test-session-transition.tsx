"use client";

import { moduleTranslationKeys } from "@/lib/i18n/translations";
import { useTranslation } from "@/lib/i18n/locale-provider";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import type { TestSession } from "@/lib/api/test-sessions";
import { advanceTestSession } from "@/lib/api/test-sessions";
import { clearAttemptDraft, isTerminalAttempt } from "./exam-draft-recovery";

export function TestSessionTransition({ initial }: { initial: TestSession }) {
  const { t } = useTranslation();
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<import("@/lib/i18n/types").TranslationKey>();
  const last = initial.attempts.at(-1);
  useEffect(() => {
    initial.attempts.filter((attempt) => isTerminalAttempt(attempt.status))
      .forEach((attempt) => clearAttemptDraft(attempt.attempt_id));
  }, [initial.attempts]);
  async function advance() {
    setPending(true); setError(undefined);
    try {
      const next = await advanceTestSession(initial.session_id);
      if (next.current_attempt) router.push(`/attempt/${next.current_attempt.attempt_id}`);
      else router.refresh();
    } catch { setError("runner.continueMockError"); setPending(false); }
  }
  if (initial.status === "COMPLETED") return <div className="session-transition"><p className="practice-module-kicker">{t("runner.mockComplete")}</p><h1>{initial.test_title}</h1><p>{t("runner.mockDescription")}</p><div className="session-score-grid">{initial.attempts.map((item) => <div key={item.attempt_id}><span>{t(moduleTranslationKeys[item.module])}</span><strong>{item.band_score?.toFixed(1) ?? "—"}</strong></div>)}<div><span>{t("runner.overall")}</span><strong>{initial.overall_band_score?.toFixed(1) ?? "—"}</strong></div></div><Link className="btn btn-primary" href="/history">{t("runner.viewResults")}</Link></div>;
  const completedLabel = last ? t(moduleTranslationKeys[last.module]) : t("runner.module");
  const nextLabel = initial.next_module ? t(moduleTranslationKeys[initial.next_module]) : t("runner.nextModule");
  return <div className="session-transition"><p className="practice-module-kicker">{t("runner.fullMock")}</p><h1>{t("runner.moduleComplete", { module: completedLabel })}</h1><p>{t("runner.next")} <strong>{nextLabel}</strong></p>{initial.warnings.map((warning) => <p className="notice" key={warning}>{warning}</p>)}<button type="button" className="btn btn-primary" disabled={pending} onClick={() => void advance()}>{pending ? t("runner.preparing") : t("runner.continueTo", { module: nextLabel })}</button>{error ? <p role="alert" className="notice notice-error">{t(error)}</p> : null}</div>;
}
