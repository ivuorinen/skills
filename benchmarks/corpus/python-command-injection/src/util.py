"""Unrelated helpers that also mention subprocess."""

import subprocess


def git_sha():
    """Safe: fixed argv, no shell, output captured."""
    out = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True)
    return out.stdout.strip()


def docker_available():
    """Safe: fixed argv."""
    return subprocess.run(["docker", "--version"], capture_output=True).returncode == 0
