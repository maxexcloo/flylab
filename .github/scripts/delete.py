import os
import subprocess


def app_exists(app):
    return (
        subprocess.run(
            ["flyctl", "apps", "info", app],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
        == 0
    )


def main():
    app = os.environ["APP"]
    if not app_exists(app):
        print(f"{app} does not exist")
        return

    subprocess.run(["flyctl", "apps", "destroy", app, "--yes"], check=True)


if __name__ == "__main__":
    main()
