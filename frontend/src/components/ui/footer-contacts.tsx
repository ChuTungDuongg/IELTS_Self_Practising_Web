import { UiText } from "@/lib/i18n/locale-provider";

const contacts = [
  { name: "LinkedIn", url: "https://www.linkedin.com/in/duongchunguyen/", path: "M20.45 2H3.55C2.69 2 2 2.68 2 3.52v16.96c0 .84.69 1.52 1.55 1.52h16.9c.86 0 1.55-.68 1.55-1.52V3.52c0-.84-.69-1.52-1.55-1.52ZM7.93 18.75H4.98V9.2h2.95v9.55ZM6.45 7.9a1.71 1.71 0 1 1 0-3.42 1.71 1.71 0 0 1 0 3.42Zm12.3 10.85H15.8V14.1c0-1.11-.02-2.53-1.54-2.53-1.55 0-1.79 1.21-1.79 2.45v4.73H9.52V9.2h2.83v1.31h.04a3.1 3.1 0 0 1 2.79-1.53c2.98 0 3.57 1.96 3.57 4.51v5.26Z" },
  { name: "Facebook", url: "https://www.facebook.com/rendezvouss0344/", path: "M22 12a10 10 0 1 0-11.56 9.88v-6.99H7.9V12h2.54V9.8c0-2.5 1.49-3.9 3.77-3.9 1.1 0 2.24.2 2.24.2v2.46h-1.26c-1.24 0-1.63.77-1.63 1.56V12h2.78l-.45 2.89h-2.33v6.99A10 10 0 0 0 22 12Z" },
  { name: "Zalo", url: "https://zalo.me/0367365703", path: null },
] as const;

export function FooterContacts() {
  return <div className="footer-contacts">
    <p className="footer-contact-title"><UiText message="footer.connect" /></p>
    <ul className="footer-social-links">
      {contacts.map(contact => <li key={contact.name}>
        <a href={contact.url} target="_blank" rel="noopener noreferrer" aria-label={contact.name} title={contact.name}>
          <svg viewBox={contact.path ? "0 0 24 24" : "0 0 40 24"} width="24" height="24" fill="currentColor" aria-hidden="true" focusable="false" data-brand={contact.name}>
            {contact.path ? <path d={contact.path} /> : <text x="1" y="17" fontFamily="Arial, sans-serif" fontSize="16" fontWeight="700" letterSpacing="-1">Zalo</text>}
          </svg>
        </a>
      </li>)}
    </ul>
    <p className="footer-phone">Zalo: <a href="tel:+84367365703">0367365703</a></p>
  </div>;
}
