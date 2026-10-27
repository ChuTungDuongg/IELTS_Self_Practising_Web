import { render, type RenderResult } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { LocaleProvider, useLocale } from "@/lib/i18n/locale-provider";

export function LocaleControls(): ReactElement {
  const { setLocale } = useLocale();
  return <><button onClick={() => setLocale("en")}>Switch to English</button><button onClick={() => setLocale("vi")}>Switch to Vietnamese</button></>;
}

export function renderWithLocale(ui: ReactElement): RenderResult {
  return render(ui, { wrapper: ({ children }: { children: ReactNode }) => <LocaleProvider>{children}<LocaleControls /></LocaleProvider> });
}
