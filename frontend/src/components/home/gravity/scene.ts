import * as THREE from "three";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";
import { createField, modes, PALETTES, qualityFor, resizeField, ROLES, smoothstep, tick, type FieldPointer } from "./physics";

export type GravityScene = {
  setActive(active: boolean): void;
  setProgress(progress: number): void;
  setPointer(x: number, y: number, down: boolean, active: boolean): void;
  scatter(): void;
  dispose(): void;
};

/** Loaded only by the homepage effect. No DOM, timers or GPU resources at module scope. */
export function createGravityScene(container: HTMLElement, lowPower: boolean, onReady: () => void, onFailure: () => void): GravityScene {
  const disposers: Array<() => void> = [];
  const releaseResources = () => {
    for (const dispose of disposers.splice(0).reverse()) {
      try { dispose(); } catch { /* One driver failure must not skip the other resources. */ }
    }
  };
  try {
  const quality = qualityFor(container.clientWidth, lowPower);
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(38, 1, .1, 100);
  camera.position.set(0, 0, 11);
  const renderer = new THREE.WebGLRenderer({ antialias: !lowPower, alpha: true, powerPreference: lowPower ? "low-power" : "default" });
  disposers.push(() => { renderer.renderLists.dispose(); renderer.dispose(); renderer.forceContextLoss(); renderer.domElement.remove(); });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, quality.dpr));
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.15;
  renderer.shadowMap.enabled = quality.shadows;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.setClearColor(0x000000, 0);
  container.appendChild(renderer.domElement);

  const hemi = new THREE.HemisphereLight(0xffffff, 0x2f69ff, 1.6);
  const key = new THREE.DirectionalLight(0xffffff, 1.4);
  key.position.set(-6, 10, 8); key.castShadow = quality.shadows;
  key.shadow.mapSize.set(1024, 1024);
  Object.assign(key.shadow.camera, { near: .5, far: 30, left: -8, right: 8, top: 8, bottom: -8 });
  key.shadow.bias = -.0003; key.shadow.radius = 12;
  disposers.push(() => key.shadow.map?.dispose());
  const rim = new THREE.DirectionalLight(0xffffff, 1.25); rim.position.set(8, 7, -8);
  const front = new THREE.DirectionalLight(0xffffff, .4); front.position.set(0, 0, 11);
  const bounce = new THREE.DirectionalLight(0xffffff, .3); bounce.position.set(-9, -2, 4);
  scene.add(hemi, key, rim, front, bounce);

  // Procedural studio reflections, generated once; no image/model downloads.
  let environment: THREE.WebGLRenderTarget | undefined;
  if (!lowPower) {
    const studio = new RoomEnvironment();
    const generator = new THREE.PMREMGenerator(renderer);
    try { environment = generator.fromScene(studio, .04); scene.environment = environment.texture; disposers.push(() => environment?.dispose()); }
    finally { studio.dispose(); generator.dispose(); }
  }
  const geometry = new THREE.SphereGeometry(1, quality.segments, quality.segments);
  disposers.push(() => geometry.dispose());
  const field = createField(quality.count, 10, 7);
  const palette = Object.fromEntries(ROLES.map((role, index) => [role, {
    hero: new THREE.Color(PALETTES.hero[index]), lime: new THREE.Color(PALETTES.lime[index]), pink: new THREE.Color(PALETTES.pink[index]), current: new THREE.Color(),
  }])) as Record<typeof ROLES[number], { hero: THREE.Color; lime: THREE.Color; pink: THREE.Color; current: THREE.Color }>;
  const meshes = field.bodies.map(body => {
    const color = palette[body.role].hero;
    const material = new THREE.MeshPhysicalMaterial(body.glass ? {
      color, roughness: .08, metalness: 0, clearcoat: 1, clearcoatRoughness: .03,
      transmission: lowPower ? 0 : .95, opacity: lowPower ? .66 : 1, ior: 1.485, thickness: 2.2,
      specularColor: new THREE.Color("#ffffff"), specularIntensity: 1,
      attenuationColor: palette.pastel.hero, attenuationDistance: 1,
      emissive: color, emissiveIntensity: .12, transparent: true,
    } : {
      color, roughness: .44, metalness: 0, clearcoat: .24, clearcoatRoughness: .35,
      emissive: color, emissiveIntensity: .08, transparent: true,
    });
    disposers.push(() => material.dispose());
    const mesh = new THREE.Mesh(geometry, material);
    mesh.scale.setScalar(body.radius); mesh.castShadow = quality.shadows; mesh.receiveShadow = quality.shadows;
    mesh.position.set(body.position.x, body.position.y, body.position.z);
    scene.add(mesh); return mesh;
  });
  const floorGeometry = new THREE.PlaneGeometry(200, 200);
  const floorMaterial = new THREE.ShadowMaterial({ opacity: .1 });
  disposers.push(() => floorGeometry.dispose(), () => floorMaterial.dispose());
  const floor = new THREE.Mesh(floorGeometry, floorMaterial);
  floor.rotation.x = -Math.PI / 2; floor.receiveShadow = true; floor.visible = quality.shadows;
  scene.add(floor);

  let disposed = false, active = false, progress = 0, targetProgress = 0, frame = 0, previousTime = 0, accumulator = 0, ready = false;
  let pointerX = 99, pointerY = 99, pointerActive = false, pointerDown = false, burstUntil = 0;
  let lastX = 0, lastY = 0, hadPointer = false;
  const pointer: FieldPointer = { x: 0, y: 0, z: 0, active: false, down: false, speed: 0 };
  const axis = new THREE.Vector3();
  const resize = () => {
    if (disposed) return;
    const width = Math.max(1, container.clientWidth), height = Math.max(1, container.clientHeight);
    camera.aspect = width / height; camera.updateProjectionMatrix();
    renderer.setSize(width, height, false);
    const frustumHeight = 2 * Math.tan(THREE.MathUtils.degToRad(38) / 2) * 11;
    resizeField(field, frustumHeight * camera.aspect, frustumHeight);
    floor.position.y = -frustumHeight / 2 + .04;
  };
  const resizeObserver = new ResizeObserver(resize);
  disposers.push(() => resizeObserver.disconnect());
  resizeObserver.observe(container); resize();
  const contextLost = (event: Event) => { event.preventDefault(); stop(); onFailure(); };
  renderer.domElement.addEventListener("webglcontextlost", contextLost);
  disposers.push(() => renderer.domElement.removeEventListener("webglcontextlost", contextLost));

  function stop() { active = false; cancelAnimationFrame(frame); frame = 0; previousTime = 0; accumulator = 0; }
  function animate(now: number) {
    frame = 0;
    if (!active || disposed) return;
    // Fixed 60 Hz dynamics, max 3 catch-up ticks; no refresh-rate-dependent physics.
    const elapsed = previousTime ? Math.min((now - previousTime) / 1000, .05) : 1 / 60;
    accumulator += elapsed;
    previousTime = now;
    progress += (targetProgress - progress) * (1 - Math.exp(-elapsed * 9));
    const burst = now < burstUntil;
    pointer.x = burst ? 0 : pointerX * field.width / 2;
    pointer.y = burst ? 0 : pointerY * field.height / 2;
    pointer.active = burst || pointerActive; pointer.down = burst || pointerDown;
    pointer.speed = burst ? 2 : hadPointer ? Math.min(3, Math.hypot(pointer.x - lastX, pointer.y - lastY)) : 0;
    lastX = pointer.x; lastY = pointer.y; hadPointer = pointer.active;
    while (accumulator >= 1 / 60) { tick(field, progress, pointer); accumulator -= 1 / 60; pointer.speed = 0; }
    const mode = modes(progress);
    for (const role of ROLES) palette[role].current.copy(palette[role].hero).lerp(palette[role].lime, mode.lime).lerp(palette[role].pink, mode.pink);
    hemi.groundColor.copy(palette.medium.current);
    for (const body of field.bodies) {
      const mesh = meshes[body.id], material = mesh.material;
      const dx = body.position.x - mesh.position.x, dy = body.position.y - mesh.position.y;
      const movement = Math.hypot(dx, dy);
      if (movement > .00001) { axis.set(dy, -dx, 0).normalize(); mesh.rotateOnWorldAxis(axis, movement / body.radius * .95); }
      mesh.position.set(body.position.x, body.position.y, body.position.z);
      mesh.scale.setScalar(body.scale);
      material.color.copy(palette[body.role].current); material.emissive.copy(palette[body.role].current);
      if (body.glass) material.attenuationColor.copy(palette.pastel.current);
      material.opacity = (body.glass && lowPower ? .66 : 1) * (mode.fly > .001 ? 1 - smoothstep(8.4, 10.7, body.position.z) : 1);
      mesh.visible = material.opacity > .005 && body.position.z < 11;
    }
    try {
      renderer.render(scene, camera);
      if (!ready) { ready = true; onReady(); }
    } catch { stop(); onFailure(); return; }
    // All spheres have left the lens. Sleep until scrolling/visibility resumes us.
    if (mode.fly > .98 && field.bodies.every(body => body.position.z >= 12)) return;
    frame = requestAnimationFrame(animate);
  }
  return {
    setActive(value) {
      if (disposed || value === active && (!value || frame !== 0)) return;
      if (!value) { stop(); return; }
      active = true; frame = requestAnimationFrame(animate);
    },
    setProgress(value) { targetProgress = value; if (active && !frame) { previousTime = 0; frame = requestAnimationFrame(animate); } },
    setPointer(x, y, down, enabled) { pointerX = x; pointerY = y; pointerDown = down; pointerActive = enabled; },
    scatter() { burstUntil = performance.now() + 240; },
    dispose() {
      if (disposed) return;
      disposed = true; stop(); scene.environment = null; scene.clear(); releaseResources();
    },
  };
  } catch (error) {
    releaseResources();
    throw error;
  }
}
