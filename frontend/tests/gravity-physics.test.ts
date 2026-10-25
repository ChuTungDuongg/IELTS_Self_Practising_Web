// @vitest-environment node
import { describe, expect, it } from "vitest";
import { backgroundStage, createField, inHeart, modes, qualityFor, resizeField, tick } from "@/components/home/gravity/physics";

describe("Gravity reference physics", () => {
  it("preserves reference phases and palette thresholds", () => {
    expect(modes(0)).toMatchObject({ hero: 1, drop: 0, shape: 0, fly: 0 });
    expect(modes(1).drop).toBe(1);
    expect(modes(2.1).shape).toBe(1);
    expect(modes(3.5).fly).toBe(1);
    expect([0, .71, 1.56].map(backgroundStage)).toEqual([0, 1, 2]);
  });
  it("uses seeded, bounded bodies with radius-cubed mass and valid heart targets", () => {
    const field = createField(96, 12, 7);
    expect(field.bodies).toEqual(createField(96, 12, 7).bodies);
    for (const body of field.bodies) {
      expect(body.radius).toBeGreaterThanOrEqual(.27); expect(body.radius).toBeLessThan(.87);
      expect(body.mass).toBeCloseTo(body.radius ** 3);
      const size = Math.min(12 * .3, 7 * .27);
      expect(inHeart(body.target.x / size, (body.target.y + 7 * .03) / size - .12)).toBe(true);
    }
    resizeField(field, 4, 8);
    expect(field.shapeScale).toBeGreaterThanOrEqual(.3);
  });
  it("falls, bounces, converges on the heart and releases toward the lens", () => {
    const field = createField(12, 12, 7);
    for (let i = 0; i < 300; i++) tick(field, 0);
    for (let i = 0; i < 300; i++) tick(field, 1);
    expect(field.bodies.every(b => b.position.y - b.scale >= -3.45 - .001)).toBe(true);
    expect(field.bodies.reduce((sum, b) => sum + b.position.y, 0) / 12).toBeLessThan(-1);
    for (let i = 0; i < 300; i++) tick(field, 2.1);
    expect(Math.max(...field.bodies.map(b => Math.hypot(b.position.x - b.target.x, b.position.y - b.target.y)))).toBeLessThan(.4);
    for (let i = 0; i < 120; i++) tick(field, 3.5);
    expect(field.bodies.every(b => b.position.z > 11)).toBe(true);
    tick(field, 2.1);
    expect(field.bodies.every(b => Math.abs(b.position.z) <= 2)).toBe(true);
  });
  it("separates coincident bodies and transfers mass-weighted contact impulses", () => {
    const field = createField(2, 12, 7);
    for (const body of field.bodies) { body.position = { x: 0, y: 0, z: 0 }; }
    tick(field, 0);
    expect(Math.abs(field.bodies[0].position.x - field.bodies[1].position.x)).toBeGreaterThan(.1);
    expect(field.bodies.every(b => Number.isFinite(b.velocity.x))).toBe(true);
  });
  it("adds cursor momentum without making the simulation non-finite", () => {
    const slow = createField(1, 12, 7), fast = createField(1, 12, 7);
    for (const f of [slow, fast]) { f.bodies[0].position = { x: 1, y: 0, z: 0 }; }
    tick(slow, 2.1, { x: 0, y: 0, z: 0, active: true, down: false, speed: 0 });
    tick(fast, 2.1, { x: 0, y: 0, z: 0, active: true, down: false, speed: 3 });
    expect(fast.bodies[0].velocity.x).toBeGreaterThan(slow.bodies[0].velocity.x);
  });
  it("reduces GPU work for mobile and low-power devices", () => {
    expect(qualityFor(1440, false).count).toBe(96);
    expect(qualityFor(390, false).count).toBe(54);
    expect(qualityFor(1440, true)).toMatchObject({ count: 32, dpr: 1, shadows: false });
  });
  it("parks released spheres instead of growing unbounded during a long pause", () => {
    const field = createField(1, 12, 7);
    for (let i = 0; i < 12000; i++) tick(field, 3.5);
    expect(field.bodies[0].position.z).toBe(12);
    expect(Object.values(field.bodies[0].position).every(Number.isFinite)).toBe(true);
    tick(field, 0);
    expect(field.bodies[0].position.z).toBeLessThan(2);
  });
});
