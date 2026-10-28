import type { VersionDetail } from "@/lib/api/schema";

const requiredModules = ["LISTENING", "READING", "WRITING", "SPEAKING"] as const;

/** Mirrors the module and duration prerequisites checked when a Full Mock session starts.
 * The server still makes the final authorization and runtime decision. */
export function fullMockEligibility(modules: VersionDetail["modules"]) {
  const missing = requiredModules.find(type => !modules.some(module => module.module_type === type));
  const missingDuration = modules.find(module => !module.recommended_duration_seconds || module.recommended_duration_seconds <= 0);
  return { missing, missingDuration, available: !missing && !missingDuration };
}
