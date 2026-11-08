"""AGENTS.md sections 3.2 and 3.3: ignore files, line endings and editor settings."""

from __future__ import annotations

import fnmatch

import pytest
from support.defects import defect
from support.repo import REPO_ROOT, active_lines, project_files, read

# Entries both ignore files must carry whenever the matching tool/path exists in the project.
SHARED_ENTRIES = [
    ".env",
    "__pycache__/",
    ".venv/",
    ".pytest_cache/",
    ".mypy_cache/",
    ".ruff_cache/",
    ".coverage",
    "htmlcov/",
    ".import_linter_cache/",
    ".cache/",
]
GITIGNORE_ONLY = [".hypothesis/", "*.pem", "*.key", "secrets/"]


def normalised(lines: list[str]) -> set[str]:
    return {line.rstrip("/") for line in lines} | set(lines)


class TestGitignore:
    @pytest.mark.parametrize("entry", SHARED_ENTRIES + GITIGNORE_ONLY)
    def test_required_entry_present(self, entry: str) -> None:
        stem = entry.rstrip("/")
        present = normalised(active_lines(".gitignore"))
        assert (
            entry in present
            or stem in present
            or f"{stem}*" in present
            or any(fnmatch.fnmatch(stem, p.rstrip("/")) for p in present if "*" in p)
        ), f".gitignore is missing {entry}"

    def test_env_example_is_not_ignored(self) -> None:
        assert "!.env.example" in active_lines(".gitignore")

    def test_the_real_env_file_is_ignored_in_every_variant(self) -> None:
        lines = active_lines(".gitignore")
        assert ".env" in lines and ".env.*" in lines


class TestDockerignore:
    @pytest.mark.parametrize("entry", SHARED_ENTRIES)
    def test_required_entry_present(self, entry: str) -> None:
        stem = entry.rstrip("/")
        present = normalised(active_lines(".dockerignore"))
        assert entry in present or stem in present or f"{stem}*" in present, (
            f".dockerignore is missing {entry}"
        )

    def test_secrets_never_enter_the_build_context(self) -> None:
        lines = active_lines(".dockerignore")
        assert ".env" in lines and ".env.*" in lines and "!.env.example" in lines

    def test_vcs_and_ci_metadata_stay_out_of_images(self) -> None:
        lines = active_lines(".dockerignore")
        assert ".git" in lines and ".github" in lines

    def test_test_artifacts_stay_out_of_images(self) -> None:
        lines = " ".join(active_lines(".dockerignore"))
        assert ".pytest_cache" in lines and ".coverage" in lines

    def test_ml_weight_caches_are_ignored_by_both_files(self) -> None:
        git, docker = " ".join(active_lines(".gitignore")), " ".join(active_lines(".dockerignore"))
        for cache in (".cache/", "hf_cache", "flashrank_cache"):
            assert cache in docker, f".dockerignore is missing {cache}"
        assert ".cache/" in git

    def test_the_two_files_agree_on_python_artifacts(self) -> None:
        git, docker = set(active_lines(".gitignore")), set(active_lines(".dockerignore"))
        for entry in (
            "__pycache__/",
            "*.py[cod]",
            ".venv/",
            ".ruff_cache/",
            ".mypy_cache/",
            ".import_linter_cache/",
        ):
            assert entry in git and entry in docker, entry


class TestGitattributes:
    @pytest.mark.parametrize(
        "pattern", ["*.py", "*.sh", "*.sql", "Dockerfile*", "*.yaml", "*.yml", "*.toml"]
    )
    def test_eol_lf_is_enforced(self, pattern: str) -> None:
        rules = {line.split()[0]: line.split()[1:] for line in active_lines(".gitattributes")}
        assert "eol=lf" in rules.get(pattern, []), f"{pattern} must be `text eol=lf`"

    def test_binary_artifacts_are_not_text_normalised(self) -> None:
        rules = {line.split()[0]: line.split()[1:] for line in active_lines(".gitattributes")}
        for pattern in ("*.pdf", "*.onnx", "*.safetensors"):
            assert "binary" in rules.get(pattern, [])


class TestWorkingTreeLineEndings:
    """The point of .gitattributes: scripts must be LF so containers never see ``\\r`` in a shebang."""

    @pytest.mark.parametrize(
        "pattern", ["*.sh", "*.sql", "Dockerfile*", "*.Dockerfile", "*.yaml", "*.yml", "*.toml"]
    )
    def test_files_use_lf(self, pattern: str) -> None:
        crlf = [
            str(p.relative_to(REPO_ROOT))
            for p in project_files(pattern)
            if b"\r\n" in p.read_bytes()
        ]
        assert not crlf, f"CRLF line endings in: {crlf}"

    def test_python_sources_use_lf(self) -> None:
        crlf = [
            str(p.relative_to(REPO_ROOT))
            for p in project_files("*.py")
            if b"\r\n" in p.read_bytes()
        ]
        assert not crlf, f"CRLF line endings in: {crlf[:10]}"

    def test_shell_scripts_have_a_shebang_and_strict_mode(self) -> None:
        for script in project_files("*.sh"):
            text = script.read_text(encoding="utf-8")
            assert text.startswith("#!"), f"{script.name} lacks a shebang"
            assert "set -" in text, f"{script.name} should fail fast (set -e...)"

    def test_text_files_are_utf8_without_bom(self) -> None:
        for path in project_files("*.py", "*.md", "*.yaml", "*.yml", "*.toml", "*.sql", "*.sh"):
            assert not path.read_bytes().startswith(b"\xef\xbb\xbf"), (
                f"BOM in {path.relative_to(REPO_ROOT)}"
            )


class TestEditorConfig:
    def test_declares_lf_and_utf8(self) -> None:
        text = read(".editorconfig")
        assert "end_of_line = lf" in text and "charset = utf-8" in text

    def test_root_flag_is_set(self) -> None:
        assert read(".editorconfig").lstrip().startswith("root = true")


class TestPackaging:
    def test_python_version_is_pinned_consistently(self) -> None:
        import tomllib

        pyproject = tomllib.loads(read("pyproject.toml"))
        requires = pyproject["project"]["requires-python"]
        assert "3.12" in requires
        assert "python:3.12" in read("infra/docker/api.Dockerfile")

    def test_strict_markers_are_on_and_every_tier_is_registered(self) -> None:
        import tomllib

        ini = tomllib.loads(read("pyproject.toml"))["tool"]["pytest"]["ini_options"]
        assert "--strict-markers" in ini["addopts"]
        registered = {m.split(":")[0].strip() for m in ini["markers"]}
        assert {
            "unit",
            "integration",
            "graph",
            "security",
            "e2e",
            "hygiene",
            "eval",
            "gpu",
            "slow",
            "defect",
            "live",
        } <= registered


class TestDockerfile:
    @defect("DEFECT-12")
    def test_the_source_is_copied_before_the_package_is_installed(self) -> None:
        lines = read("infra/docker/api.Dockerfile").splitlines()
        install = next(
            i for i, line in enumerate(lines) if "uv pip install" in line and "-e ." in line
        )
        copy_src = next(
            i for i, line in enumerate(lines) if line.startswith("COPY") and "src/" in line
        )
        assert copy_src < install, (
            "COPY src/ must precede `uv pip install -e .` so the editable install sees the code"
        )


class TestDeclaredDependencies:
    @defect("DEFECT-35")
    def test_multipart_support_is_declared_when_the_api_takes_uploads(self) -> None:
        uses_multipart = any(
            "UploadFile" in p.read_text(encoding="utf-8")
            or "File(" in p.read_text(encoding="utf-8")
            for p in (REPO_ROOT / "src" / "ragassist").rglob("*.py")
        )
        if not uses_multipart:
            pytest.skip("PENDING: no multipart upload route is mounted yet")
        assert "python-multipart" in read("pyproject.toml"), (
            "python-multipart is used but not declared"
        )


class TestConfigurationHygiene:
    @defect("DEFECT-37")
    def test_queue_names_come_from_settings_not_literals(self) -> None:
        offenders = [
            str(path.relative_to(REPO_ROOT))
            for path in (REPO_ROOT / "src" / "ragassist").rglob("*.py")
            if path.name != "settings.py"
            and '"ragassist-ingest"' in path.read_text(encoding="utf-8")
        ]
        assert not offenders, f"hard-coded queue names (use SQS_QUEUE_INGEST): {offenders}"


class TestPortUsage:
    @defect("DEFECT-40")
    def test_ingestion_uses_the_object_store_port_methods(self) -> None:
        source = (
            REPO_ROOT
            / "src"
            / "ragassist"
            / "modules"
            / "knowledge"
            / "application"
            / "ingestion_service.py"
        )
        text = source.read_text(encoding="utf-8")
        wrong = [name for name in ("self.store.delete(",) if name in text]
        assert not wrong, f"use the ObjectStore port name delete_object, not {wrong}"
