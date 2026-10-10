export function PageHeading({
  eyebrow,
  eyebrowClassName,
  title,
  description,
  action,
}: {
  eyebrow?: React.ReactNode;
  eyebrowClassName?: string;
  title: React.ReactNode;
  description?: React.ReactNode;
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
