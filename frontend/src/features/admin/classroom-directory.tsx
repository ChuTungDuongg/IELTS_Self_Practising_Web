"use client";

import Link from "next/link";
import { PageHeading } from "@/components/ui/page-heading";
import { useTranslation } from "@/lib/i18n/locale-provider";
import type { DirectoryClassroomsPage, DirectoryPeoplePage, DirectoryPerson, DirectoryRole } from "@/lib/api/admin-directory";
import type { TranslationKey } from "@/lib/i18n/types";
import styles from "./classroom-directory.module.css";

type Filters = {
  role: DirectoryRole; personId?: string; search: string; classroomSearch: string;
  peopleOffset: number; classroomOffset: number;
};

function directoryHref(filters: Filters) {
  const query = new URLSearchParams({ role: filters.role });
  if (filters.personId) query.set("person", filters.personId);
  if (filters.search) query.set("search", filters.search);
  if (filters.classroomSearch) query.set("classroomSearch", filters.classroomSearch);
  if (filters.peopleOffset) query.set("peopleOffset", String(filters.peopleOffset));
  if (filters.classroomOffset) query.set("classroomOffset", String(filters.classroomOffset));
  return `/admin/classrooms?${query.toString()}`;
}

function SearchContext({ filters, scope }: { filters: Filters; scope: "people" | "classrooms" }) {
  return <>
    <input type="hidden" name="role" value={filters.role} />
    {filters.personId ? <input type="hidden" name="person" value={filters.personId} /> : null}
    {scope === "people" && filters.classroomSearch ? <input type="hidden" name="classroomSearch" value={filters.classroomSearch} /> : null}
    {scope === "classrooms" && filters.search ? <input type="hidden" name="search" value={filters.search} /> : null}
    {scope === "classrooms" && filters.peopleOffset ? <input type="hidden" name="peopleOffset" value={filters.peopleOffset} /> : null}
  </>;
}

function DirectoryPagination({ page, filters, scope }: {
  page: { total: number; offset: number; limit: number }; filters: Filters; scope: "people" | "classrooms";
}) {
  const { t } = useTranslation();
  if (page.total <= page.limit && page.offset === 0) return null;
  const field = scope === "people" ? "peopleOffset" : "classroomOffset";
  return <nav className={styles.pagination} aria-label={t(scope === "people" ? "directory.peoplePages" : "directory.classroomPages")}>
    {page.offset > 0 ? <Link className="btn btn-secondary" prefetch={false} href={directoryHref({ ...filters, [field]: Math.max(0, page.offset - page.limit) })}>{t("common.previous")}</Link> : <span />}
    <span>{page.offset >= page.total ? t("directory.emptyPage") : t("directory.pageRange", { start: page.offset + 1, end: Math.min(page.offset + page.limit, page.total), total: page.total })}</span>
    {page.offset + page.limit < page.total ? <Link className="btn btn-secondary" prefetch={false} href={directoryHref({ ...filters, [field]: page.offset + page.limit })}>{t("common.next")}</Link> : <span />}
  </nav>;
}

export function AdminClassroomDirectory({ people, classrooms, selectedPerson, filters }: {
  people: DirectoryPeoplePage; classrooms: DirectoryClassroomsPage; selectedPerson: DirectoryPerson | null; filters: Filters;
}) {
  const { t } = useTranslation();
  const peopleTitle: TranslationKey = filters.role === "TEACHER" ? "directory.teachers" : "directory.students";
  const searchLabel: TranslationKey = filters.role === "TEACHER" ? "directory.searchTeachers" : "directory.searchStudents";
  return <div className={styles.directory}>
    <PageHeading eyebrow={t("admin.administration")} title={t("directory.title")} description={t("directory.description")} action={<Link href="/admin" className="btn btn-secondary">{t("directory.accountAdministration")}</Link>} />
    <p className={`notice ${styles.observerNotice}`}>{t("directory.observerNotice")}</p>
    <nav className={styles.roleNavigation} aria-label={t("directory.peopleType")}>
      <Link href="/admin/classrooms?role=TEACHER" aria-current={filters.role === "TEACHER" ? "page" : undefined}>{t("directory.teachers")}</Link>
      <Link href="/admin/classrooms?role=USER" aria-current={filters.role === "USER" ? "page" : undefined}>{t("directory.students")}</Link>
    </nav>
    {selectedPerson ? <Link className={`btn btn-ghost ${styles.mobileBack}`} href={directoryHref({ ...filters, personId: undefined, classroomOffset: 0 })}>{t("directory.backToPeople")}</Link> : null}
    <div className={styles.columns}>
      <section className={`surface-card ${styles.panel}${selectedPerson ? ` ${styles.selectedPeoplePanel}` : ""}`} aria-labelledby="directory-people-heading">
        <div className={styles.panelHeading}><h2 id="directory-people-heading">{t(peopleTitle)}</h2><span>{t("directory.peopleCount", { count: people.total })}</span></div>
        <form role="search" aria-label={t(searchLabel)} action="/admin/classrooms" method="get" className={styles.search}>
          <SearchContext filters={filters} scope="people" />
          <label><span>{t(searchLabel)}</span><input className="field" type="search" name="search" defaultValue={filters.search} maxLength={160} /></label>
          <button className="btn btn-secondary" type="submit">{t("common.search")}</button>
        </form>
        {people.items.length ? <ul className={styles.people}>{people.items.map(person => <li key={person.id}>
          <Link className={styles.person} prefetch={false} href={directoryHref({ ...filters, personId: person.id, classroomOffset: 0 })} aria-current={person.id === selectedPerson?.id ? "true" : undefined}>
            <span className={styles.personName}>{person.display_name}</span>
            <span className={styles.personDetails}><span>{t("directory.classroomCount", { count: person.classroom_count })}</span>{!person.is_active ? <span>{t("profile.inactive")}</span> : null}</span>
          </Link>
        </li>)}</ul> : <p className={styles.empty}>{t("directory.noPeople")}</p>}
        <DirectoryPagination page={people} filters={filters} scope="people" />
      </section>
      <section className={`surface-card ${styles.panel}`} aria-labelledby="directory-classrooms-heading">
        <div className={styles.panelHeading}><div><h2 id="directory-classrooms-heading">{selectedPerson ? t(filters.role === "TEACHER" ? "directory.teacherClassrooms" : "directory.studentClassrooms", { name: selectedPerson.display_name }) : t("directory.allClassrooms")}</h2><p>{t("directory.classroomCount", { count: classrooms.total })}</p></div>{selectedPerson ? <Link className="btn btn-ghost" href={directoryHref({ ...filters, personId: undefined, classroomOffset: 0 })}>{t("directory.clearPerson")}</Link> : null}</div>
        <form role="search" aria-label={t("directory.searchClassrooms")} action="/admin/classrooms" method="get" className={styles.search}>
          <SearchContext filters={filters} scope="classrooms" />
          <label><span>{t("directory.searchClassrooms")}</span><input className="field" type="search" name="classroomSearch" defaultValue={filters.classroomSearch} maxLength={160} /></label>
          <button className="btn btn-secondary" type="submit">{t("common.search")}</button>
        </form>
        {classrooms.items.length ? <ul className={styles.classrooms}>{classrooms.items.map(classroom => <li key={classroom.id} className={styles.classroom}>
          <div className={styles.classroomIdentity}><h3>{classroom.name}</h3><span className={styles.status}>{t(classroom.status === "ACTIVE" ? "directory.active" : "common.archived")}</span></div>
          <p>{t("directory.owner", { name: classroom.teacher.display_name })}</p>
          <p className={styles.enrolled}>{t("directory.enrolledCount", { count: classroom.enrolled_student_count })}</p>
          <div className={styles.actions}><Link className="btn btn-secondary" prefetch={false} href={`/classrooms/${encodeURIComponent(classroom.id)}`}>{t("directory.observe")}</Link><Link className="btn btn-ghost" prefetch={false} href={`/classrooms/${encodeURIComponent(classroom.id)}?tab=people`}>{t("directory.roster")}</Link></div>
        </li>)}</ul> : <p className={styles.empty}>{t("directory.noClassrooms")}</p>}
        <DirectoryPagination page={classrooms} filters={filters} scope="classrooms" />
      </section>
    </div>
  </div>;
}
