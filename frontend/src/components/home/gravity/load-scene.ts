/** The only runtime entry into Three.js; called after browser preference checks. */
export async function loadGravityScene() {
  return import("./scene");
}
