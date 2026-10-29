import type { ReactNode } from "react";
import { AuthHero } from "./auth-hero";
import { AuthProductIllustration } from "./auth-product-illustration";
import styles from "./auth.module.css";

export function AuthLayout({ children }: { children: ReactNode }) {
  return <div className={styles.experience}>
    <AuthHero><AuthProductIllustration /></AuthHero>
    <div className={styles.formColumn}>{children}</div>
  </div>;
}
