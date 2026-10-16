import subprocess
from pathlib import Path

from fly import python_command


def main():
    directories = [Path("tests")]
    directories.extend(
        path.parent / "tests" for path in sorted(Path(".").glob("*/deployment.toml"))
    )
    for directory in directories:
        if directory.is_dir():
            subprocess.run(
                [
                    *python_command(directory.parent),
                    "python",
                    "-B",
                    "-m",
                    "unittest",
                    "discover",
                    "-s",
                    str(directory),
                ],
                check=True,
            )


if __name__ == "__main__":
    main()
