import subprocess
import shlex
import logging
import datetime
import re
import os
import sys
from typing import Tuple, List, Optional, Dict, Union

# --------------------------------------------------------------------
# Custom Exceptions
# --------------------------------------------------------------------
class CommandExecutionError(Exception):
    """Raised when a shell command fails to execute or returns a non-zero exit code."""
    def __init__(self, command: str, exit_code: int, stdout: str, stderr: str):
        self.command = command
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr
        super().__init__(f"Command '{command}' failed with exit code {exit_code}")

class SafetyCheckError(Exception):
    """Raised when a destructive command is detected and not confirmed."""
    def __init__(self, command: str):
        self.command = command
        super().__init__(f"Safety check failed: command '{command}' is potentially destructive.")

# --------------------------------------------------------------------
# Logging Configuration
# --------------------------------------------------------------------
def _configure_logger(audit_file: Optional[str] = None) -> logging.Logger:
    """
    Configure a logger that logs to console and optionally to an audit file.
    """
    logger = logging.getLogger("terminal_control_skill")
    if logger.handlers:
        return logger  # Already configured

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # File handler for audit logs
    if audit_file:
        fh = logging.FileHandler(audit_file)
        fh.setLevel(logging.INFO)
        fh.setFormatter(formatter)
        logger.addHandler(fh)

    return logger

# --------------------------------------------------------------------
# Safety Checks
# --------------------------------------------------------------------
_DESTRUCTIVE_PATTERNS = [
    r"rm\s+-rf\b",
    r"dd\s+if=",
    r"chmod\s+777\b",
    r"wipe\s+-p\s+\d+",
    r"mkfs\s+",
    r"dd\s+of=",
    r"truncate\s+",
    r"dd\s+if=",
    r"dd\s+of=",
    r"shred\s+",
    r"dd\s+if=",
    r"dd\s+of=",
    r"dd\s+if=",
    r"dd\s+of=",
    r"dd\s+if=",
    r"dd\s+of=",
    r"dd\s+if=",
    r"dd\s+of=",
    r"dd\s+if=",
    r"dd\s+of=",
    r"dd\s+if=",
    r"dd\s+of=",
    r"dd\s+if=",
    r"dd\s+of=",
    r"dd\s+if=",
    r"dd\s+of=",
    r"dd\s+if=",
    r"dd\s+of=",
    r"dd\s+if=",
    r"dd\s+of=",
]

def _is_destructive(command: str) -> bool:
    """
    Return True if the command matches any destructive pattern.
    """
    for pattern in _DESTRUCTIVE_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return True
    return False

def _confirm_destructive(command: str) -> None:
    """
    Prompt the user for confirmation if the command is potentially destructive.
    Raises SafetyCheckError if the user declines.
    """
    print(f"WARNING: The command '{command}' looks destructive.")
    resp = input("Do you want to proceed? (y/N): ").strip().lower()
    if resp != "y":
        raise SafetyCheckError(command)

# --------------------------------------------------------------------
# Core Function
# --------------------------------------------------------------------
def execute_command(
    command: Union[str, List[str]],
    *,
    stdin: Optional[bytes] = None,
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    sudo: bool = False,
    timeout: Optional[int] = None,
    audit_file: Optional[str] = None,
    confirm: bool = True,
) -> Tuple[str, str, int]:
    """
    Execute a shell command with optional parameters.

    Parameters
    ----------
    command : str or list of str
        The command to execute. If a string, it will be split safely using shlex.
    stdin : bytes, optional
        Data to send to the command's stdin.
    cwd : str, optional
        Working directory for the command.
    env : dict, optional
        Environment variables for the command. Merged with the current environment.
    sudo : bool, default False
        If True, prepend 'sudo' to the command. Requires appropriate permissions.
    timeout : int, optional
        Timeout in seconds for the command execution.
    audit_file : str, optional
        Path to a file where audit logs will be written.
    confirm : bool, default True
        If True, perform safety check and prompt for confirmation on destructive commands.

    Returns
    -------
    stdout : str
        Standard output of the command.
    stderr : str
        Standard error of the command.
    exit_code : int
        Exit code returned by the command.

    Raises
    ------
    SafetyCheckError
        If the command is destructive and not confirmed.
    CommandExecutionError
        If the command fails to execute or returns a non-zero exit code.
    subprocess.TimeoutExpired
        If the command exceeds the specified timeout.
    """
    logger = _configure_logger(audit_file)

    # Ensure command is a list for subprocess.run
    if isinstance(command, str):
        cmd_list = shlex.split(command)
    else:
        cmd_list = command

    # Prepend sudo if requested
    if sudo:
        cmd_list = ["sudo"] + cmd_list

    # Convert to string for logging and safety checks
    cmd_str = " ".join(shlex.quote(part) for part in cmd_list)

    # Safety check
    if confirm and _is_destructive(cmd_str):
        _confirm_destructive(cmd_str)

    logger.info(f"Executing command: {cmd_str}")

    # Prepare environment
    proc_env = os.environ.copy()
    if env:
        proc_env.update(env)

    try:
        result = subprocess.run(
            cmd_list,
            input=stdin,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            env=proc_env,
            shell=False,
            timeout=timeout,
            text=True
        )
        stdout = result.stdout
        stderr = result.stderr
        exit_code = result.returncode

        logger.info(f"Command exited with {exit_code}")
        if stdout:
            logger.info(f"STDOUT: {stdout.strip()}")
        if stderr:
            logger.error(f"STDERR: {stderr.strip()}")

        if exit_code != 0:
            raise CommandExecutionError(cmd_str, exit_code, stdout, stderr)

        return stdout, stderr, exit_code

    except subprocess.TimeoutExpired as te:
        logger.error(f"Command timed out after {timeout} seconds.")
        raise te

    except Exception as e:
        logger.exception("Unexpected error during command execution.")
        raise e

# --------------------------------------------------------------------
# Example Usage
# --------------------------------------------------------------------
if __name__ == "__main__":
    # Simple test: list current directory
    try:
        out, err, code = execute_command(
            "ls -l",
            timeout=5,
            audit_file="audit.log",
            confirm=False
        )
        print("Output:")
        print(out)
    except Exception as exc:
        print(f"Error: {exc}")

    # Destructive command example (will prompt)
    try:
        out, err, code = execute_command(
            "rm -rf /tmp/some_nonexistent_dir",
            confirm=True,
            audit_file="audit.log"
        )
    except SafetyCheckError as sce:
        print(f"Safety check prevented execution: {sce}")

    # Unit tests
    import unittest

    class TestTerminalControlSkill(unittest.TestCase):
        def test_basic_command(self):
            out, err, code = execute_command("echo 'hello world'", timeout=2, confirm=False)
            self.assertEqual(code, 0)
            self.assertIn("hello world", out.strip())

        def test_non_zero_exit(self):
            with self.assertRaises(CommandExecutionError):
                execute_command("false", timeout=2, confirm=False)

        def test_timeout(self):
            with self.assertRaises(subprocess.TimeoutExpired):
                execute_command("sleep 5", timeout=1, confirm=False)

        def test_sudo_simulation(self):
            # This test assumes the user has sudo rights without password prompt.
            # If not, it will raise a subprocess.CalledProcessError.
            try:
                out, err, code = execute_command("whoami", sudo=True, timeout=2, confirm=False)
                self.assertEqual(code, 0)
            except subprocess.CalledProcessError:
                self.skipTest("User does not have sudo rights without password.")

        def test_safety_check(self):
            with self.assertRaises(SafetyCheckError):
                execute_command("rm -rf /", confirm=True, audit_file=None)

    unittest.main(argv=[sys.argv[0]], exit=False)