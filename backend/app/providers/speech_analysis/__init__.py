"""One analysis per continuous normalized segment, reusable by all consumers."""

from app.providers.speech_analysis.azure import AzureSpeechAnalyzer

__all__ = ["AzureSpeechAnalyzer"]
