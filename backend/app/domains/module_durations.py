from app.models.enums import ModuleType


def default_module_duration(module_type: ModuleType) -> int:
    return {
        ModuleType.READING: 3600,
        ModuleType.LISTENING: 1800,
        ModuleType.WRITING: 3600,
    }[module_type]
