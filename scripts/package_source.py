"""Package only authored source/configuration, never credentials or analysis data."""

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "outputs" / "Global-Segregation-Atlas.zip"
EXCLUDE = {
    "node_modules",
    ".next",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "test-results",
    "playwright-report",
}
ROOT_FILES = {
    "README.md",
    ".env.example",
    ".gitignore",
    ".editorconfig",
    "docker-compose.yml",
}


def sources():
    for name in sorted(ROOT_FILES):
        yield ROOT / name
    for top in ("apps", "docs", "scripts"):
        for path in sorted((ROOT / top).rglob("*")):
            relative = path.relative_to(ROOT)
            if not path.is_file() or any(
                part in EXCLUDE or part.endswith(".egg-info") for part in relative.parts
            ):
                continue
            if path.name.startswith(".env") or path.suffix in {".pyc", ".tsbuildinfo"}:
                continue
            yield path


def main():
    OUTPUT.parent.mkdir(exist_ok=True)
    secrets = []
    local_env = ROOT / ".env"
    if local_env.exists():
        for line in local_env.read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("=")
            if (
                key.endswith("_API_KEY") or key == "PLACE_TOKEN_SECRET"
            ) and value.strip():
                secrets.append(value.strip().encode())
    files = list(sources())
    for path in files:
        content = path.read_bytes()
        if any(secret in content for secret in secrets):
            raise RuntimeError(
                f"Credential detected; refusing to package {path.relative_to(ROOT)}"
            )
    with ZipFile(OUTPUT, "w", ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(
                path, "global-segregation-atlas/" + path.relative_to(ROOT).as_posix()
            )
    with ZipFile(OUTPUT) as archive:
        assert not any(name.endswith("/.env") for name in archive.namelist())
        assert archive.testzip() is None
    print(
        f"Packaged {len(files)} source files, {OUTPUT.stat().st_size:,} bytes. Credential scan passed."
    )


if __name__ == "__main__":
    main()
