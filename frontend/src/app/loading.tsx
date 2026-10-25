import { UiText } from "@/lib/i18n/locale-provider";

export default function Loading() {
  return <div className="workspace-loading" role="status" aria-busy="true">
    <p><UiText message="ui.loading" /></p>
    <div aria-hidden="true">
      <span className="skeleton skeleton-title" />
      <span className="skeleton skeleton-line" />
      <div className="skeleton-grid">{[0, 1, 2].map(index => <div key={index} className="skeleton-panel"><span className="skeleton" /><span className="skeleton skeleton-line" /></div>)}</div>
    </div>
  </div>;
}
