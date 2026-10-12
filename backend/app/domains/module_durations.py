from app.models.enums import ModuleType


def default_module_duration(module_type: ModuleType) -> int:
    return {
        ModuleType.READING: 3600,
        ModuleType.LISTENING: 1800,
        ModuleType.WRITING: 3600,
        # A configurable application recommendation. Prompt timers remain authoritative.
        ModuleType.SPEAKING: 900,
    }[module_type]
