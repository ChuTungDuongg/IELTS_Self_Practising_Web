import { fireEvent, render, screen } from "@testing-library/react";
import { renderWithLocale } from "./locale-test-utils";
import { describe, expect, it } from "vitest";
import { BuilderWorkspaceNavigation } from "@/features/test-builder/builder-workspace-navigation";

const testId = "11111111-1111-4111-8111-111111111111";
const versionId = "22222222-2222-4222-8222-222222222222";

describe("Builder workspace navigation", () => {
  it("localizes the selected workspace without changing link nodes or destinations", () => {
    window.localStorage.clear();
    renderWithLocale(<BuilderWorkspaceNavigation testId={testId} versionId={versionId} workspace="listening" moduleTypes={["READING"]} />);
    const links = screen.getAllByRole("link");
    const hrefs = links.map((link) => link.getAttribute("href"));
    fireEvent.click(screen.getByText("Switch to Vietnamese"));
    expect(screen.getByRole("complementary", { name: "Các phần biên soạn" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /NgheChưa tạo/ })).toBe(links[2]);
    expect(links[2]).toHaveAttribute("aria-current", "page");
    expect(screen.getAllByRole("link")).toEqual(links);
    expect(links.map((link) => link.getAttribute("href"))).toEqual(hrefs);
  });
  it("uses URL-backed navigation and follows the selected workspace", () => {
    render(<BuilderWorkspaceNavigation testId={testId} versionId={versionId} workspace="listening" moduleTypes={["READING"]} />);

    expect(screen.getByRole("link", { name: /Overview/ })).toHaveAttribute(
      "href",
      `/admin/tests/${testId}/versions/${versionId}/edit?workspace=overview`,
    );
    expect(screen.getByRole("link", { name: /Reading/ })).toHaveClass("builder-workspace-reading");
    expect(screen.getByRole("link", { name: /Reading/ })).not.toHaveAttribute("aria-current");
    expect(screen.getByRole("link", { name: /Listening/ })).toHaveClass("builder-workspace-listening");
    expect(screen.getByRole("link", { name: /Listening/ })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: /WritingNot created/ })).toHaveAttribute(
      "href",
      `/admin/tests/${testId}/versions/${versionId}/edit?workspace=writing`,
    );
    expect(screen.getByRole("link", { name: /ReadingCreated/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /ListeningNot created/ })).toBeInTheDocument();
  });

  it("keeps Listening navigable when it has not been created", () => {
    render(<BuilderWorkspaceNavigation testId={testId} versionId={versionId} workspace="overview" />);
    expect(screen.getByRole("link", { name: /Listening/ })).toHaveAttribute(
      "href",
      `/admin/tests/${testId}/versions/${versionId}/edit?workspace=listening`,
    );
    expect(screen.getByRole("link", { name: /Writing/ })).toBeInTheDocument();
  });
});
