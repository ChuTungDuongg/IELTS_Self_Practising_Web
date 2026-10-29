"use client";

import { useId, useState } from "react";
import { useTranslation } from "@/lib/i18n/locale-provider";
import { AuthIcon } from "./auth-icons";
import styles from "./auth.module.css";

type PasswordFieldProps = {
  name: "password" | "confirm_password";
  label: string;
  autoComplete: "current-password" | "new-password";
  minLength: number;
  hint?: string;
  invalid?: boolean;
  errorId?: string;
};

export function PasswordField({ name, label, autoComplete, minLength, hint, invalid, errorId }: PasswordFieldProps) {
  const { t } = useTranslation();
  const id = useId();
  const [visible, setVisible] = useState(false);
  const describedBy = [hint ? `${id}-help` : null, invalid ? errorId : null].filter(Boolean).join(" ") || undefined;

  return <div className={styles.field}>
    <label htmlFor={id}>{label}</label>
    <div className={styles.inputWrap}>
      <AuthIcon name="lock" className={styles.leadingIcon} />
      <input id={id} name={name} type={visible ? "text" : "password"} required minLength={minLength} autoComplete={autoComplete} aria-describedby={describedBy} aria-invalid={invalid || undefined} className={styles.passwordInput} />
      <button type="button" className={styles.passwordToggle} aria-label={t(visible ? "auth.hidePassword" : "auth.showPassword", { field: label })} aria-controls={id} onClick={() => setVisible(current => !current)}>
        <AuthIcon name={visible ? "eyeOff" : "eye"} />
      </button>
    </div>
    {hint ? <p id={`${id}-help`} className={styles.passwordHint}>{hint}</p> : null}
  </div>;
}
