export function PageHeading({
  eyebrow,
  eyebrowClassName,
  title,
  description,
  action,
}: {
  eyebrow?: string;
  eyebrowClassName?: string;
  title: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="page-heading">
      <div className="max-w-3xl">
        {eyebrow ? (
          <p className={`page-eyebrow page-context-kicker ${eyebrowClassName ?? ""}`.trim()}>
            {eyebrow}
          </p>
        ) : null}
        <h1>{title}</h1>
        {description ? <p className="page-description">{description}</p> : null}
      </div>
      {action ? <div className="page-heading-action">{action}</div> : null}
    </div>
  );
}
