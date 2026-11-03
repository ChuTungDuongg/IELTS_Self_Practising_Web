/** Stable domain codes only; never render provider bodies or infer a monthly allowance. */
export function speakingServiceErrorKey(code: string | null | undefined) {
  if (code === "SPEAKING_AZURE_QUOTA_EXCEEDED" || code === "AZURE_QUOTA_EXCEEDED") {
    return "speakingService.quotaExceeded" as const;
  }
  if (code === "SPEAKING_AZURE_BILLING_NOT_AUTHORIZED") {
    return "speakingService.billingBlocked" as const;
  }
  if (code === "SPEAKING_AZURE_AUTHENTICATION_FAILED") {
    return "speakingService.authenticationFailed" as const;
  }
  return null;
}
