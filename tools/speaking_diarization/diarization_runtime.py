"""Standard-library bootstrap shared by the isolated worker and its developer CLI."""

import importlib
import importlib.metadata
import os
import socket
import sys
from pathlib import Path

# FFmpeg major -> avcodec, avformat, avutil, swresample, swscale ABI majors.
FFMPEG_ABIS = {
    7: (61, 61, 59, 5, 8),
    6: (60, 60, 58, 4, 7),
    5: (59, 59, 57, 4, 6),
    4: (58, 58, 56, 3, 5),
}
DLL_HANDLES = []


class StageError(Exception):
    def __init__(self, code, stage, error=None):
        self.code, self.stage = "REPLAY_DIARIZATION_" + code, stage
        name = type(error).__name__ if error is not None else "RuntimeError"
        self.exception_class = name if name.isidentifier() and len(name) <= 64 else "Exception"
        super().__init__(self.code)

    def payload(self):
        return {
            "schema_version": 1,
            "error_code": self.code,
            "stage": self.stage,
            "exception_class": self.exception_class,
        }


def package_versions(identity):
    if os.name == "nt" and not os.environ.get("SYSTEMROOT"):
        raise StageError("WINDOWS_SYSTEMROOT_MISSING", "windows_bootstrap")
    if sys.version_info[:2] != (3, 12):
        raise StageError("PYTHON_VERSION_UNSUPPORTED", "python")
    result = {}
    for name, wanted in identity["versions"].items():
        try:
            actual = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError as error:
            raise StageError("PACKAGE_MISSING", "packages", error) from None
        if actual.split("+")[0] != wanted:
            raise StageError("PACKAGE_VERSION_INCOMPATIBLE", "packages")
        result[name] = actual
    return result


def local_directory(value):
    if not value or not isinstance(value, str) or any(c in value for c in ("\0", "\n", "\r")):
        return None
    if value.startswith(("\\\\", "//")) or "://" in value:
        return None
    try:
        path = Path(value.strip('"')).expanduser()
        return path.resolve() if path.is_absolute() and path.is_dir() else None
    except (OSError, ValueError):
        return None


def shared_major(directory):
    if directory is None:
        return None
    for major, versions in FFMPEG_ABIS.items():
        names = zip(
            ("avcodec", "avformat", "avutil", "swresample", "swscale"), versions, strict=True
        )
        if all((directory / f"{name}-{version}.dll").is_file() for name, version in names):
            return major
    return None


def ffmpeg_candidates(environ, home):
    # Bounded path-only discovery; no recursive disk search or Conda subprocess/activation.
    path_entries = [local_directory(p) for p in environ.get("PATH", "").split(";")[:128]]
    yield from (p for p in path_entries if p)
    prefix = local_directory(environ.get("CONDA_PREFIX"))
    if prefix:
        yield prefix / "Library/bin"
    bases = []
    if prefix:
        bases.append(prefix.parent.parent if prefix.parent.name.lower() == "envs" else prefix)
    conda_exe = environ.get("CONDA_EXE", "")
    if conda_exe:
        bases.append(Path(conda_exe).parent.parent)
    for entry in path_entries:
        if entry:
            bases.extend([entry, *list(entry.parents)[:3]])
    for parent in (
        home,
        local_directory(environ.get("LOCALAPPDATA")),
        local_directory(environ.get("PROGRAMDATA")),
    ):
        if parent:
            bases.extend(
                parent / name for name in ("anaconda3", "miniconda3", "miniforge3", "mambaforge")
            )
    registry = home / ".conda/environments.txt"
    try:
        if registry.is_file() and registry.stat().st_size <= 65536:
            for entry in registry.read_text(encoding="utf-8").splitlines()[:128]:
                prefix = local_directory(entry)
                if prefix:
                    yield prefix / "Library/bin"
    except (OSError, UnicodeError):
        pass
    seen = set()
    for base in bases[:1024]:
        if base in seen:
            continue
        seen.add(base)
        if not (base / "conda-meta").is_dir() and not (base / "envs").is_dir():
            continue
        yield base / "Library/bin"
        try:
            yield from (
                p / "Library/bin" for p in sorted((base / "envs").iterdir())[:128] if p.is_dir()
            )
        except OSError:
            pass


def resolve_ffmpeg(*, environ=None, home=None, windows=None):
    if windows is None:
        windows = os.name == "nt"
    if not windows:
        return None, None
    environ = os.environ if environ is None else environ
    home = Path.home() if home is None else Path(home)
    explicit = environ.get("BANDPILOT_FFMPEG_DLL_DIR")
    if explicit:
        path = local_directory(explicit)
        major = shared_major(path)
        if major is None:
            raise StageError("FFMPEG_OVERRIDE_INVALID", "ffmpeg_discovery")
        return path, major
    for candidate in ffmpeg_candidates(environ, home):
        major = shared_major(candidate)
        if major is not None:
            return candidate.resolve(), major
    raise StageError("FFMPEG_SHARED_DLLS_MISSING", "ffmpeg_discovery")


def native_imports(*, windows=None):
    directory, major = resolve_ffmpeg(windows=windows)
    if directory is not None:
        try:
            DLL_HANDLES.append(os.add_dll_directory(str(directory)))
        except OSError as error:
            raise StageError(
                "FFMPEG_DLL_REGISTRATION_FAILED", "ffmpeg_registration", error
            ) from None
    modules = {}
    for name, stage, code in (
        ("torch", "torch_import", "TORCH_NATIVE_LOAD_FAILED"),
        ("torchcodec", "torchcodec_import", "TORCHCODEC_NATIVE_LOAD_FAILED"),
        ("pyannote.audio", "pyannote_import", "PYANNOTE_NATIVE_LOAD_FAILED"),
    ):
        try:
            modules[name] = importlib.import_module(name)
        except ModuleNotFoundError as error:
            raise StageError("PACKAGE_MISSING", stage, error) from None
        except Exception as error:
            raise StageError(code, stage, error) from None
    return modules, {"ffmpeg_shared_major": major, "native_imports": "OK"}


def forbid_network():
    def blocked(*_args, **_kwargs):
        raise OSError("Offline diarization forbids network access")

    socket.socket.connect = blocked
    socket.socket.connect_ex = blocked
    socket.create_connection = blocked
    socket.getaddrinfo = blocked


def download_error(error):
    # Inspect structured HTTP status / exception types only, never messages or signed URLs.
    chain, current = [], error
    for _ in range(8):
        if current is None or any(current is item for item in chain):
            break
        chain.append(current)
        current = current.__cause__ or current.__context__
    names = {type(item).__name__ for item in chain}
    statuses = {getattr(getattr(item, "response", None), "status_code", None) for item in chain}
    if 401 in statuses:
        code = "HF_AUTHENTICATION_FAILED"
    elif 403 in statuses or "GatedRepoError" in names:
        code = "HF_GATED_ACCESS_DENIED"
    elif "RevisionNotFoundError" in names:
        code = "HF_REVISION_NOT_FOUND"
    elif names & {"SSLError", "SSLCertVerificationError", "CertificateError"}:
        code = "HF_SSL_FAILED"
    elif "ProxyError" in names:
        code = "HF_PROXY_FAILED"
    elif names & {
        "ConnectionError",
        "ConnectTimeout",
        "ReadTimeout",
        "Timeout",
        "TimeoutError",
        "gaierror",
    }:
        code = "HF_NETWORK_FAILED"
    elif names & {"EntryNotFoundError", "LocalEntryNotFoundError", "RemoteEntryNotFoundError"}:
        code = "HF_FILE_NOT_FOUND"
    elif any(
        isinstance(item, (PermissionError, FileNotFoundError, NotADirectoryError))
        or getattr(item, "errno", None) in {13, 28, 30}
        for item in chain
    ):
        code = "MODEL_STORAGE_UNWRITABLE"
    else:
        code = "HF_DOWNLOAD_FAILED"
    return StageError(code, "model_download", error)
