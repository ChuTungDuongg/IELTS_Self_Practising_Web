import { randomBytes, randomUUID } from "node:crypto";
import { expect, type APIRequestContext, type Page } from "@playwright/test";

export const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";
if (!["localhost", "127.0.0.1", "[::1]"].includes(new URL(apiBase).hostname)) {
  throw new Error("Golden-path fixtures may only run against a local API.");
}

type Module = "LISTENING" | "READING" | "WRITING";
type TestRecord = { id: string; versions: Array<{ id: string }> };
type BuilderModule = {
  id: string;
  revision: number;
  writing_tasks: Array<{ id: string; revision: number; task_number: number }>;
};
export type PublishedExam = { testId: string; versionId: string; title: string };

async function post<T>(request: APIRequestContext, path: string, data?: unknown): Promise<T> {
  const response = await request.post(`${apiBase}${path}`, data === undefined ? {} : { data });
  expect(response.ok(), `${path}: ${response.status()} ${await response.text()}`).toBe(true);
  return await response.json() as T;
}

function silentWav(): Buffer {
  const samples = 8000;
  const wav = Buffer.alloc(44 + samples * 2);
  wav.write("RIFF", 0);
  wav.writeUInt32LE(wav.length - 8, 4);
  wav.write("WAVEfmt ", 8);
  wav.writeUInt32LE(16, 16);
  wav.writeUInt16LE(1, 20);
  wav.writeUInt16LE(1, 22);
  wav.writeUInt32LE(8000, 24);
  wav.writeUInt32LE(16000, 28);
  wav.writeUInt16LE(2, 32);
  wav.writeUInt16LE(16, 34);
  wav.write("data", 36);
  wav.writeUInt32LE(samples * 2, 40);
  return wav;
}

export async function signInFixtureAdmin(request: APIRequestContext): Promise<void> {
  const email = process.env.E2E_ADMIN_EMAIL;
  const password = process.env.E2E_ADMIN_PASSWORD;
  if (!email || !password) throw new Error("Set E2E_ADMIN_EMAIL and E2E_ADMIN_PASSWORD for local E2E fixtures.");
  await post(request, "/auth/login", { email, password });
}

export async function createPublishedExam(request: APIRequestContext, modules: Module[]): Promise<PublishedExam> {
  const title = `E2E Golden ${randomUUID().slice(0, 8)}`;
  const created = await post<TestRecord>(request, "/tests", {
    title, description: "Fictional browser workflow fixture.", create_initial_draft: true,
  });
  const versionId = created.versions[0].id;
  try {
    for (const moduleType of modules) {
      const builderModule = await post<BuilderModule>(request, `/test-versions/${versionId}/modules`, {
        module_type: moduleType,
        title: moduleType.charAt(0) + moduleType.slice(1).toLowerCase(),
        recommended_duration_seconds: moduleType === "LISTENING" ? 1800 : 3600,
      });
      if (moduleType === "LISTENING") {
        const upload = await request.post(`${apiBase}/assets/audio`, {
          multipart: {
            test_version_id: versionId,
            file: { name: "fictional-silence.wav", mimeType: "audio/wav", buffer: silentWav() },
          },
        });
        expect(upload.ok(), `audio upload: ${upload.status()} ${await upload.text()}`).toBe(true);
        const asset = await upload.json() as { id: string };
        const attached = await request.put(`${apiBase}/listening/modules/${builderModule.id}/audio`, {
          data: { asset_id: asset.id, expected_revision: builderModule.revision },
        });
        expect(attached.ok(), `attach audio: ${attached.status()} ${await attached.text()}`).toBe(true);
        for (const index of [0, 1]) {
          const part = await post<{ id: string }>(request, `/test-versions/${versionId}/listening/parts`, {
            title: `Fictional section ${index + 1}`, order_index: index,
          });
          await post(request, `/listening/parts/${part.id}/question-groups`, {
            question_type: "true_false_not_given", instruction: "Choose an answer to the fictional statement.",
            config: {}, order_index: 0,
            questions: [{ id: randomUUID(), number: index + 1, prompt: `Fictional sound statement ${index + 1}.`,
              config: {}, answer_key: { kind: "SINGLE_OPTION", value: "TRUE" }, order_index: 0 }],
          });
        }
      }
      if (moduleType === "READING") {
        const passage = await post<{ id: string }>(request, `/test-versions/${versionId}/reading/passages`, {
          title: "A fictional observatory", order_index: 0,
          blocks: [{ id: randomUUID(), type: "paragraph", label: "A", text: "The fictional observatory counts stars each night." }],
        });
        await post(request, `/reading/passages/${passage.id}/question-groups`, {
          question_type: "true_false_not_given", instruction: "Choose an answer to the fictional statement.",
          config: {}, order_index: 0,
          questions: [{ id: randomUUID(), number: 1, prompt: "The fictional observatory counts stars.",
            config: {}, answer_key: { kind: "SINGLE_OPTION", value: "TRUE" }, order_index: 0 }],
        });
      }
      if (moduleType === "WRITING") {
        for (const task of builderModule.writing_tasks) {
          const response = await request.put(`${apiBase}/writing/tasks/${task.id}`, {
            data: {
              expected_revision: task.revision,
              prompt: task.task_number === 1
                ? "Describe a fictional library's weekly visitor chart."
                : "Explain whether fictional towns should build more public gardens.",
              image_asset_id: null,
              minimum_recommended_words: task.task_number === 1 ? 150 : 250,
              recommended_duration_seconds: task.task_number === 1 ? 1200 : 2400,
            },
          });
          expect(response.ok(), `writing task: ${response.status()} ${await response.text()}`).toBe(true);
        }
      }
    }
    const validation = await post<{ valid: boolean; issues: unknown[] }>(request, `/test-versions/${versionId}/validate`);
    expect(validation.valid, JSON.stringify(validation.issues)).toBe(true);
    await post(request, `/test-versions/${versionId}/publish`);
    return { testId: created.id, versionId, title };
  } catch (error) {
    await deleteFixtureTest(request, created.id);
    throw error;
  }
}

export async function registerFixtureLearner(page: Page): Promise<{ id: string }> {
  const suffix = randomBytes(8).toString("hex");
  const registered = await page.request.post(`${apiBase}/auth/register`, {
    data: {
      email: `e2e-golden-${suffix}@example.com`, display_name: `Golden Learner ${suffix}`,
      password: randomBytes(24).toString("base64url"),
    },
  });
  expect(registered.status(), await registered.text()).toBe(201);
  const user = await registered.json() as { user: { id: string } };
  return { id: user.user.id };
}

async function deleteFixtureTest(request: APIRequestContext, testId: string): Promise<void> {
  const deleted = await request.delete(`${apiBase}/tests/${testId}`);
  expect(deleted.ok(), `delete test: ${deleted.status()} ${await deleted.text()}`).toBe(true);
  const result = await deleted.json() as { action: "ARCHIVED" | "DELETED" };
  if (result.action === "ARCHIVED") {
    const permanent = await request.delete(`${apiBase}/tests/${testId}/permanent`);
    expect(permanent.status(), await permanent.text()).toBe(204);
  }
}

export async function cleanUpFixture(request: APIRequestContext, exam: PublishedExam, learnerId?: string): Promise<void> {
  try {
    if (learnerId) {
      const deactivated = await request.patch(`${apiBase}/admin/users/${learnerId}`, { data: { is_active: false } });
      expect(deactivated.ok(), `deactivate learner: ${deactivated.status()} ${await deactivated.text()}`).toBe(true);
      const deleted = await request.delete(`${apiBase}/admin/users/${learnerId}`);
      expect(deleted.status(), await deleted.text()).toBe(204);
    }
  } finally {
    await deleteFixtureTest(request, exam.testId);
  }
}

export function captureBrowserErrors(page: Page): () => void {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(`pageerror: ${error.message}`));
  page.on("console", (message) => { if (message.type() === "error") errors.push(`console: ${message.text()}`); });
  return () => expect(errors).toEqual([]);
}
