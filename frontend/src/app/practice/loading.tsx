import { UiText } from "@/lib/i18n/locale-provider";

export default function Loading() {
  return <p role="status"><UiText message="common.loading" /></p>;
}
