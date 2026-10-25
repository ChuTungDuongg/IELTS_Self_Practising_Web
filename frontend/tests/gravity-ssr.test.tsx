// @vitest-environment node
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { GravityLanding } from "@/components/home/gravity/gravity-landing";

describe("Gravity without JavaScript", () => {
  it("server-renders the content, four skill links and procedural still without WebGL", () => {
    const html = renderToStaticMarkup(<GravityLanding />);
    expect(html).toContain("Practice with purpose.");
    expect(html).toContain("Progress with confidence.");
    expect(html.match(/data-gravity-section=/g)).toHaveLength(4);
    expect(html.match(/class="gravity-static-sphere /g)).toHaveLength(20);
    for (const skill of ["READING", "LISTENING", "WRITING", "SPEAKING"]) expect(html).toContain(`/practice?skill=${skill}`);
    expect(html).toContain('href="/library"');
    expect(html).toContain('href="/history"');
    expect(html).not.toContain("<canvas");
    expect(html).not.toContain("home-orbit");
  });
});
