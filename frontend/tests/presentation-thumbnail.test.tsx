import { fireEvent, render, within } from "@testing-library/react";
import { expect, it } from "vitest";
import { PresentationThumbnail } from "@/features/exam/presentation-thumbnail";

it.each(["READING", "LISTENING"] as const)("renders detailed %s previews using real question controls in an isolated desktop viewport", module => {
  const view = render(<><PresentationThumbnail module={module} mode="PRACTICE" preview={{ title: "Fictional chosen test" }} /><PresentationThumbnail module={module} mode="EXAM" preview={{ title: "Fictional chosen test" }} /></>);
  const frames = view.container.querySelectorAll("iframe");
  expect(frames).toHaveLength(2);
  frames.forEach((frame, index) => {
    fireEvent.load(frame);
    const body = frame.contentDocument!.body;
    // Parent-owned React portals need event callbacks; inert handles preview interaction.
    expect(frame).not.toHaveAttribute("sandbox");
    expect(frame).toHaveAttribute("tabindex", "-1");
    expect(frame.parentElement).toHaveAttribute("inert");
    expect(body).toHaveAttribute("inert");
    expect(within(body).getByText("BandPilot")).toBeInTheDocument();
    expect(body.querySelector(".exam-runner")).toHaveAttribute("data-presentation", index === 0 ? "PRACTICE" : "EXAM");
    expect(body).toHaveTextContent("Fictional chosen test");
    expect(body.querySelectorAll(".exam-question-target")).toHaveLength(module === "READING" ? 6 : 4);
    if (module === "READING") {
      expect(body.querySelectorAll('input[type="radio"]').length).toBe(6);
      expect(body.querySelectorAll(".reading-passage-paragraph").length).toBeGreaterThanOrEqual(3);
    } else {
      expect(body.querySelector(".player-transport svg")).toBeInTheDocument();
      expect(body.querySelector(".listening-player-exam-bar")).toBeInTheDocument();
    }
    expect(body.querySelector("audio, script")).toBeNull();
  });
});
