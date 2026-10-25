import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as THREE from "three";
import { createGravityScene } from "@/components/home/gravity/scene";

const gpu = vi.hoisted(() => ({ render: vi.fn(), dispose: vi.fn(), context: vi.fn(), lists: vi.fn(), resize: vi.fn() }));
vi.mock("three", async importOriginal => {
  const three = await importOriginal<typeof import("three")>();
  return { ...three, WebGLRenderer: class {
    domElement = document.createElement("canvas"); shadowMap = {}; renderLists = { dispose: gpu.lists };
    setPixelRatio() {} setClearColor() {} setSize = gpu.resize;
    render = gpu.render; dispose = gpu.dispose; forceContextLoss = gpu.context;
  } };
});
let frames: Map<number, FrameRequestCallback>;
let identifier = 0;
const disconnect = vi.fn();
beforeEach(() => {
  vi.clearAllMocks(); frames = new Map();
  vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => { frames.set(++identifier, callback); return identifier; });
  vi.stubGlobal("cancelAnimationFrame", (id: number) => frames.delete(id));
  vi.stubGlobal("ResizeObserver", class { observe() {} disconnect = disconnect; });
});
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });
function host() {
  const element = document.createElement("div");
  Object.defineProperties(element, { clientWidth: { value: 390 }, clientHeight: { value: 844 } });
  return element;
}
function frame(now: number) {
  const [id, callback] = [...frames][0]; frames.delete(id); callback(now);
}

describe("Three.js scene ownership (mock GPU)", () => {
  it("reports real readiness after rendering and releases every owned resource once", () => {
    const geometryDisposal = vi.spyOn(THREE.BufferGeometry.prototype, "dispose");
    const materialDisposal = vi.spyOn(THREE.Material.prototype, "dispose");
    const element = host(), ready = vi.fn();
    const scene = createGravityScene(element, true, ready, vi.fn());
    expect(ready).not.toHaveBeenCalled();
    scene.setActive(true); frame(16);
    expect(gpu.render).toHaveBeenCalledOnce(); expect(ready).toHaveBeenCalledOnce();
    const [world, camera] = gpu.render.mock.calls[0] as [THREE.Scene, THREE.PerspectiveCamera];
    expect(camera.fov).toBe(38); expect(camera.position.z).toBe(11);
    const spheres = world.children.filter(child => child instanceof THREE.Mesh && child.geometry instanceof THREE.SphereGeometry) as THREE.Mesh<THREE.SphereGeometry, THREE.MeshPhysicalMaterial>[];
    expect(spheres).toHaveLength(32);
    expect(spheres.some(sphere => sphere.material.transmission > 0)).toBe(true);
    scene.dispose(); scene.dispose();
    expect(frames.size).toBe(0); expect(element.children).toHaveLength(0);
    expect(gpu.dispose).toHaveBeenCalledOnce(); expect(gpu.context).toHaveBeenCalledOnce(); expect(gpu.lists).toHaveBeenCalledOnce();
    expect(geometryDisposal).toHaveBeenCalledTimes(2); expect(materialDisposal).toHaveBeenCalledTimes(33);
    expect(disconnect).toHaveBeenCalledOnce();
  });
  it("stops scheduling when paused and rejects activation after disposal", () => {
    const scene = createGravityScene(host(), true, vi.fn(), vi.fn());
    scene.setActive(true); expect(frames.size).toBe(1);
    scene.setActive(false); expect(frames.size).toBe(0);
    scene.setActive(true); expect(frames.size).toBe(1);
    scene.dispose(); scene.setActive(true); expect(frames.size).toBe(0);
  });
  it("cancels animation and reports GPU context loss", () => {
    const element = host(), failed = vi.fn();
    const scene = createGravityScene(element, true, vi.fn(), failed);
    scene.setActive(true);
    element.querySelector("canvas")!.dispatchEvent(new Event("webglcontextlost", { cancelable: true }));
    expect(failed).toHaveBeenCalledOnce(); expect(frames.size).toBe(0);
    scene.dispose();
  });
});
