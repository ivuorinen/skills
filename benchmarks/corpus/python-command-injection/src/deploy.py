"""Deploy helper."""

import subprocess
import sys


def build(tag):
    """Safe: argv list, no shell."""
    return subprocess.run(["docker", "build", "-t", tag, "."], check=True)


def publish(target):
    """Push the built image to a registry."""
    return subprocess.run(
        f"docker push {target}",
        shell=True,
        check=True,
    )


if __name__ == "__main__":
    build(sys.argv[1])
    publish(sys.argv[2])
