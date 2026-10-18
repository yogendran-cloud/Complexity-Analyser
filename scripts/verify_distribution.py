"""Validate release artifacts and exercise a clean, external wheel install."""

from __future__ import annotations

import email
import subprocess
import sys
import tarfile
import tempfile
import venv
import zipfile
from pathlib import Path

EXPECTED_MODULES = {
    "complexity_analyzer_empirical.py",
    "dashboard.py",
    "sample_algorithms.py",
}
EXPECTED_NAME = "complexity-analyzer-empirical"
EXPECTED_VERSION = "0.1.0"


def inspect_artifacts(wheel: Path, sdist: Path) -> None:
    if not wheel.name.endswith("-py3-none-any.whl"):
        raise AssertionError(f"Expected a pure-Python universal wheel: {wheel.name}")

    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        metadata_name = next(
            name for name in names if name.endswith(".dist-info/METADATA")
        )
        metadata = email.message_from_bytes(archive.read(metadata_name))
        modules = {name for name in names if name.endswith(".py")}
        if modules != EXPECTED_MODULES:
            raise AssertionError(f"Unexpected wheel Python modules: {modules}")
        if not any(name.endswith(".dist-info/licenses/LICENSE") for name in names):
            raise AssertionError("The wheel does not contain its MIT LICENSE file")
        if metadata["Name"] != EXPECTED_NAME:
            raise AssertionError(f"Unexpected distribution name: {metadata['Name']}")
        if metadata["Version"] != EXPECTED_VERSION:
            raise AssertionError(f"Unexpected distribution version: {metadata['Version']}")
        if metadata["Requires-Python"] != ">=3.10":
            raise AssertionError(f"Unexpected Python requirement: {metadata['Requires-Python']}")
        if metadata["License-Expression"] != "MIT":
            raise AssertionError("Wheel metadata does not declare the MIT license")
        if metadata.get_all("License-File") != ["LICENSE"]:
            raise AssertionError("Wheel metadata does not identify LICENSE")
        if metadata.get_all("Requires-Dist") != [
            'streamlit<2.0,>=1.49; extra == "dashboard"'
        ]:
            raise AssertionError("Unexpected runtime or optional dependency metadata")

    with tarfile.open(sdist, "r:gz") as archive:
        source_names = set(archive.getnames())
        if not any(name.endswith("/LICENSE") for name in source_names):
            raise AssertionError("The source distribution does not contain LICENSE")
        source_modules = {
            name.rsplit("/", 1)[-1]
            for name in source_names
            if name.rsplit("/", 1)[-1].endswith(".py")
        }
        expected_source_modules = EXPECTED_MODULES
        if source_modules != expected_source_modules:
            raise AssertionError(f"Unexpected source distribution modules: {source_modules}")
        if "complexity_analyzer.py" in source_modules:
            raise AssertionError("The old conflicting module is present in the source distribution")


def verify_clean_install(wheel: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="complexity-analyzer-install-") as temp:
        root = Path(temp)
        environment = root / "venv"
        outside_source = root / "outside-source"
        outside_source.mkdir()
        venv.EnvBuilder(with_pip=True).create(environment)
        python = environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        subprocess.run(
            [str(python), "-m", "pip", "install", "--no-deps", str(wheel)],
            check=True,
        )
        smoke_check = (
            "import importlib.util, pathlib; "
            "from complexity_analyzer_empirical import complexity; "
            "sample = lambda n: [0] * n; "
            "default_report = complexity(sample); "
            "report = complexity(sample, sizes=(10, 20), trials=1, repetitions=1); "
            "module = pathlib.Path(__import__('complexity_analyzer_empirical').__file__).resolve(); "
            "assert importlib.util.find_spec('complexity_analyzer') is None; "
            "assert 'site-packages' in str(module).lower() or 'dist-packages' in str(module).lower(); "
            "assert importlib.util.find_spec('streamlit') is None; "
            "assert len(default_report.measurements) == 5; "
            "assert default_report.measurements[-1].median_peak_memory_bytes > 0; "
            "assert len(report.measurements) == 2; "
            "assert report.measurements[-1].median_peak_memory_bytes > 0; "
            "print('Installed module:', module); "
            "print('Estimated growth:', report.estimated_complexity); "
            "print('Peak traced memory:', report.measurements[-1].median_peak_memory_bytes)"
        )
        subprocess.run(
            [str(python), "-c", smoke_check],
            cwd=outside_source,
            check=True,
        )


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("Usage: python scripts/verify_distribution.py WHEEL SDIST")
    wheel, sdist = (Path(argument).resolve() for argument in sys.argv[1:])
    inspect_artifacts(wheel, sdist)
    verify_clean_install(wheel)
    print("Distribution metadata, contents, and clean external install verified.")


if __name__ == "__main__":
    main()
