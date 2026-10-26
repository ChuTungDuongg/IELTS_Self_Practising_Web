/** Gravity reference dynamics. One tick is 1/60 s; rendering owns the accumulator. */
export type Point = { x: number; y: number; z: number };
export type PaletteRole = "pastel" | "light" | "medium" | "deep" | "glass";
export type Body = {
  id: number; radius: number; mass: number; position: Point; velocity: Point;
  target: Point; scale: number; role: PaletteRole; glass: boolean;
};
export type Field = {
  bodies: Body[]; width: number; height: number; shapeScale: number;
  time: number; previousFly: number; random: () => number;
};
export type FieldPointer = Point & { active: boolean; down: boolean; speed: number };
export const ROLES: PaletteRole[] = ["pastel", "light", "medium", "deep", "glass"];
export const PALETTES = {
  hero: ["#ECEFFF", "#A8C1FF", "#2F69FF", "#0A33BF", "#4D80FF"],
  lime: ["#FBFFE2", "#EFFE69", "#E1FC03", "#B1E200", "#DCFF32"],
  pink: ["#FFF5F4", "#FFECEB", "#FFA6B3", "#FF4D6D", "#FFA6B3"],
} as const;
export const clamp01 = (value: number) => Math.max(0, Math.min(1, value));
export function smoothstep(start: number, end: number, value: number) {
  const t = clamp01((value - start) / (end - start));
  return t * t * (3 - 2 * t);
}
const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
export function modes(progress: number) {
  return {
    hero: 1 - smoothstep(.30, .80, progress),
    drop: smoothstep(.40, .95, progress) * (1 - smoothstep(1.25, 1.75, progress)),
    shape: smoothstep(1.40, 2.05, progress) * (1 - smoothstep(2.55, 3, progress)),
    fly: smoothstep(2.7, 3.45, progress),
    lime: smoothstep(.55, 1.05, progress),
    pink: smoothstep(1.40, 1.95, progress),
  };
}
export function backgroundStage(progress: number) { return progress > 1.55 ? 2 : progress > .7 ? 1 : 0; }
export function qualityFor(width: number, lowPower: boolean) {
  return { count: lowPower ? 32 : width < 768 ? 54 : 96, segments: lowPower ? 40 : width < 768 ? 48 : 64, dpr: lowPower ? 1 : width < 768 ? 1.5 : 2, shadows: !lowPower && width >= 768 };
}
function seededRandom(seed: number) {
  return () => {
    seed |= 0; seed = seed + 0x6D2B79F5 | 0;
    let t = Math.imul(seed ^ seed >>> 15, 1 | seed);
    t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
    return ((t ^ t >>> 14) >>> 0) / 4294967296;
  };
}
export function inHeart(x: number, y: number) {
  const a = x * x + y * y - 1;
  return a * a * a - x * x * y * y * y <= 0;
}
export function resizeField(field: Field, width: number, height: number) {
  field.width = Math.max(.5, width); field.height = Math.max(.5, height);
  const size = Math.min(field.width * .30, field.height * .27);
  const meanRadius = field.bodies.reduce((sum, body) => sum + body.radius, 0) / field.bodies.length;
  field.shapeScale = Math.max(.3, Math.min(1, (size * .45 / 2.3) / meanRadius));
  for (const body of field.bodies) {
    let x: number, y: number;
    // The implicit shape has ample area; cap attempts and use a valid center on exhaustion.
    let tries = 0;
    do { x = (field.random() * 2 - 1) * 1.25; y = field.random() * 2.55 - 1.4; }
    while (!inHeart(x, y) && ++tries < 60);
    if (!inHeart(x, y)) { x = 0; y = 0; }
    body.target = { x: x * size, y: (y + .12) * size - field.height * .03, z: (field.random() - .5) * .35 };
  }
}
export function createField(count: number, width: number, height: number, seed = 25102026): Field {
  const random = seededRandom(seed);
  const bodies: Body[] = Array.from({ length: Math.max(1, count) }, (_, id) => {
    const chance = random();
    const radius = chance < .3 ? .27 + random() * .12 : chance < .8 ? .42 + random() * .18 : .66 + random() * .21;
    const glass = random() < .22;
    const colorChance = random();
    const role: PaletteRole = glass ? "glass" : colorChance < .25 ? "pastel" : colorChance < .55 ? "light" : colorChance < .85 ? "medium" : "deep";
    const angle = random() * Math.PI * 2;
    const distance = Math.max(width, height) * 1.5;
    const position = { x: Math.cos(angle) * distance * 1.25, y: Math.sin(angle) * distance * .85, z: (random() - .5) * 4 };
    const inward = (.08 + random() * .05) / Math.hypot(position.x, position.y, position.z);
    return { id, radius, mass: radius ** 3, position, velocity: { x: -position.x * inward, y: -position.y * inward, z: -position.z * inward }, target: { x: 0, y: 0, z: 0 }, scale: radius, role, glass };
  });
  const field: Field = { bodies, width, height, shapeScale: 1, time: 0, previousFly: 0, random };
  resizeField(field, width, height);
  return field;
}

export function tick(field: Field, progress: number, pointer?: FieldPointer) {
  field.time += 1 / 60;
  const mode = modes(progress);
  // Returning up the document must recover balls that already crossed the camera.
  if (field.previousFly > .02 && mode.fly <= .02) {
    for (const body of field.bodies) {
      body.position = { ...body.target }; body.velocity = { x: 0, y: 0, z: 0 };
    }
  }
  field.previousFly = mode.fly;
  const entrance = 1 - (1 - clamp01(field.time / 2.2)) ** 3;
  const attraction = .0035 * lerp(7.5, 1, entrance) * Math.max(mode.hero, entrance < 1 ? 1 : 0);
  let damping = lerp(.91, .992, mode.drop);
  damping = lerp(damping, .90, mode.shape);
  damping = lerp(damping, .985, mode.fly);
  for (const body of field.bodies) {
    const p = body.position, v = body.velocity;
    if (mode.fly > .98 && p.z >= 12) {
      p.z = 12; v.x = 0; v.y = 0; v.z = 0;
      continue;
    }
    v.x += Math.sin(field.time * .4 + body.id * 1.5) * .0004 * body.radius * mode.hero - p.x * attraction * .38;
    v.y += Math.cos(field.time * .5 + body.id * 1.2) * .0004 * body.radius * mode.hero - (p.y - field.height * .23) * attraction * 1.85 - .011 * mode.drop;
    v.z += Math.sin(field.time * .35 + body.id) * .0001 * mode.hero - p.z * attraction * 1.8;
    if (mode.shape > .001) {
      v.x += (body.target.x - p.x) * .06 * mode.shape;
      v.y += (body.target.y - p.y) * .06 * mode.shape;
      v.z += (body.target.z - p.z) * .06 * mode.shape;
    }
    if (mode.fly > .001) {
      const stagger = (body.id * .6180339887) % 1;
      const local = smoothstep(stagger * .55, stagger * .55 + .45, mode.fly);
      v.z += .05 * local; v.x += p.x * .006 * local; v.y += p.y * .006 * local;
    }
    if (pointer?.active) {
      let dx = p.x - pointer.x, dy = p.y - pointer.y, dz = p.z - pointer.z;
      const distance = Math.hypot(dx, dy, dz), radius = 4.4 * (pointer.down ? 1.4 : 1);
      if (distance < radius && distance > .0001) {
        const ratio = distance / radius;
        const push = (1 - ratio * ratio * (3 - 2 * ratio)) * .05 * (pointer.down ? 1.7 : 1) * (1 + Math.min(3, pointer.speed) * 3.2);
        dz *= .12;
        const length = Math.hypot(dx, dy, dz);
        dx /= length; dy /= length; dz /= length;
        v.x += dx * push; v.y += dy * push; v.z += dz * push;
      }
    }
    v.x *= damping; v.y *= damping; v.z *= damping;
    p.x += v.x; p.y += v.y; p.z += v.z;
    body.scale += (body.radius * (1 - (1 - field.shapeScale) * mode.shape) - body.scale) * .12;
  }
  const collideScale = .28 * (1 - .93 * mode.shape) * (1 - mode.fly);
  for (let step = 0; step < 4; step++) {
    for (let i = 0; i < field.bodies.length; i++) {
      const a = field.bodies[i];
      for (let j = i + 1; j < field.bodies.length; j++) {
        const b = field.bodies[j];
        let dx = b.position.x - a.position.x, dy = b.position.y - a.position.y, dz = b.position.z - a.position.z;
        let distance = Math.hypot(dx, dy, dz);
        const minimum = a.scale + b.scale;
        if (distance >= minimum) continue;
        // Deterministic separation also resolves exactly coincident bodies.
        if (distance < .001) { dx = .001; dy = 0; dz = 0; distance = .001; }
        dx /= distance; dy /= distance; dz /= distance;
        const overlap = minimum - distance, total = a.mass + b.mass;
        const moveA = overlap * b.mass / total * collideScale;
        const moveB = overlap * a.mass / total * collideScale;
        a.position.x -= dx * moveA; a.position.y -= dy * moveA; a.position.z -= dz * moveA;
        b.position.x += dx * moveB; b.position.y += dy * moveB; b.position.z += dz * moveB;
        const normal = (b.velocity.x - a.velocity.x) * dx + (b.velocity.y - a.velocity.y) * dy + (b.velocity.z - a.velocity.z) * dz;
        if (normal < -.0001) {
          const impulse = -1.02 * normal / (1 / a.mass + 1 / b.mass);
          a.velocity.x -= dx * impulse / a.mass; a.velocity.y -= dy * impulse / a.mass; a.velocity.z -= dz * impulse / a.mass;
          b.velocity.x += dx * impulse / b.mass; b.velocity.y += dy * impulse / b.mass; b.velocity.z += dz * impulse / b.mass;
        }
      }
    }
  }
  for (const body of field.bodies) {
    const p = body.position, v = body.velocity, r = body.scale;
    if (mode.fly < .5) {
      const bound = Math.max(r, field.width / 2 - .2);
      if (p.x < -bound - r) { p.x = -bound - r; v.x *= -.3; }
      if (p.x > bound + r) { p.x = bound + r; v.x *= -.3; }
      const floor = -field.height / 2 + .05;
      if (p.y - r < floor) {
        p.y = floor + r;
        if (v.y < 0) v.y = -v.y * (.30 + .35 * mode.drop);
        if (mode.drop > .3) { v.x *= .86; v.z *= .86; }
      }
      const top = field.height / 2 - .05;
      if (p.y + r > top) { p.y = top - r; if (v.y > 0) v.y *= -.3; }
    }
    if (mode.fly < .02) {
      if (p.z < -2) { p.z = -2; v.z *= -.3; }
      if (p.z > 2) { p.z = 2; v.z *= -.3; }
    }
  }
}
