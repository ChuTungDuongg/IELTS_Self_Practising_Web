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
  switch (code) {
    case "NO_SPEECH": return "speakingService.noSpeech" as const;
    case "TOO_SHORT": return "speakingService.speechTooShort" as const;
    case "VERY_LOW_SIGNAL": return "speakingService.lowSignal" as const;
    case "AUDIO_CORRUPT": return "speakingService.audioCorrupt" as const;
    case "SEVERE_CLIPPING": return "speakingService.audioDistorted" as const;
    case "BACKGROUND_DOMINANT": return "speakingService.backgroundNoise" as const;
    case "ASR_UNUSABLE": return "speakingService.speechUnrecognized" as const;
    case "SPEAKING_AUDIO_UNASSESSABLE": return "speakingService.audioUnavailable" as const;
    case "SPEAKING_ANALYSIS_BILLING_UNKNOWN": return "speakingService.analysisInterrupted" as const;
    case "SPEAKING_ASR_UNAVAILABLE": return "speakingService.recognitionUnavailable" as const;
    case "SPEAKING_LEXICAL_ASR_UNAVAILABLE": return "speakingService.recognitionUnavailable" as const;
    case "SPEAKING_LEXICAL_ASR_NOT_AUTHORIZED": return "speakingService.billingBlocked" as const;
    case "SPEAKING_LEXICAL_ASR_BUDGET_EXCEEDED": return "speakingService.lexicalBudgetExceeded" as const;
    case "TRANSCRIPT_SOURCE_CHANGED": return "speakingService.recordingChanged" as const;
    case "TRANSCRIPT_CONFIGURATION_CHANGED": return "speakingService.configurationChanged" as const;
    case "SPEAKING_INTERRUPTED_RETRY_NOT_AVAILABLE": return "speakingService.retryUnavailable" as const;
  }
  return null;
}
