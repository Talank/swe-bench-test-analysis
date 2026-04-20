#!/usr/bin/env python3

import logging
import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from minisweagent.exceptions import Submitted
from minisweagent.utils.serialize import recursive_merge

os.environ["LITELLM_DISABLE_TELEMETRY"] = "1"

class SingularityEnvironmentConfig(BaseModel):
    image: str
    cwd: str = "/"
    env: dict[str, str] = {}
    """Environment variables to set in the container."""
    forward_env: list[str] = []
    """Environment variables to forward to the container."""
    timeout: int = 30
    """Timeout for executing commands in the container."""
    executable: str = os.getenv("MSWEA_SINGULARITY_EXECUTABLE", "singularity")
    """Path to the singularity executable."""
    sandbox_build_retries: int = 3
    """Number of retries for building the sandbox if an error occurs."""
    global_args: list[str] = ["--quiet"]
    """Global arguments passed before the subcommand (e.g., --quiet, --debug)."""
    exec_args: list[str] = ["--contain", "--cleanenv", "--writable-tmpfs"] #"--fakeroot"]
    """Arguments passed to `singularity exec`."""


class SingularityEnvironment:
    def __init__(
        self, *, config_class: type = SingularityEnvironmentConfig, logger: logging.Logger | None = None, **kwargs
    ):
        print("USING THE MODIFIED SINGULARITY FILE")
        """Singularity environment. See `SingularityEnvironmentConfig` for kwargs."""
        self.logger = logger or logging.getLogger("minisweagent.environment")
        self.config = config_class(**kwargs)
        self.sandbox_dir = self._build_sandbox()

        self.cleaned_tests = False
    def _build_sandbox(self) -> Path:
        # Building the sandbox can fail (very rarely), so we retry it
        max_retries = self.config.sandbox_build_retries
        for attempt in range(max_retries):
            sandbox_dir = Path(tempfile.gettempdir()) / f"minisweagent-{uuid.uuid4().hex[:8]}"
            try:
                subprocess.run(
                    [self.config.executable, "build", "--sandbox", sandbox_dir, self.config.image],
                    check=True,
                    capture_output=True,
                )
                break
            except subprocess.CalledProcessError as e:
                shutil.rmtree(sandbox_dir, ignore_errors=True)
                self.logger.error(
                    f"Error building image {self.config.image}, stdout: {e.stdout}, stderr: {e.stderr} (attempt {attempt + 1}/{max_retries})"
                )
                if attempt == max_retries - 1:
                    raise
        return sandbox_dir

    def get_template_vars(self, **kwargs) -> dict[str, Any]:
        if "task" in kwargs:
            task = kwargs["task"]

            print("=== RAW TASK (repr) ===")
            print(repr(task[:200]))
            print("=======================")

            for i, c in enumerate(task[:50]):
                if ord(c) > 127:
                    print(f"NON-ASCII at pos {i}: {repr(c)}")
        return recursive_merge(self.config.model_dump(), kwargs)

    def serialize(self) -> dict:
        return {
            "info": {
                "config": {
                    "environment": self.config.model_dump(mode="json"),
                    "environment_type": f"{self.__class__.__module__}.{self.__class__.__name__}",
                }
            }
        }

    def execute(self, action: dict, cwd: str = "", *, timeout: int | None = None) -> dict[str, Any]:
        """Execute a command in a Singularity container and return the result as a dict."""
        command = action.get("command", "")

        #remove non-ASCII from command BEFORE anything else
        # if isinstance(command, str):
        #     command = command.encode("ascii", "ignore").decode()
        
        if not hasattr(self, "cleaned_tests"):
            print("INIT cleaned_tests")
            self.cleaned_tests = False

        if not self.cleaned_tests:
            print("Injecting debug + cleanup into first command")

            cleanup_cmd = (
                "echo '=== DEBUG: CURRENT DIR ==='; "
                "pwd; "
                "ls; "

                "echo '=== BEFORE TEST CLEANUP ==='; "
                "find . -iname '*test*.py' | head -20; "

                "echo '=== REMOVING TEST FILES ==='; "
                "find . -type f -iname '*test*.py' -delete; "

                "echo '=== VERIFY TEST DIR (sympy/core/tests) ==='; "
                "ls sympy/core/tests/ 2>/dev/null || echo 'dir missing'; "

                "echo '=== AFTER TEST CLEANUP ==='; "
                "find . -iname '*test*.py' | head -20"
            )
    
            command = cleanup_cmd + " ; " + command
            self.cleaned_tests = True
    # ============================================================================ 
        # ================= DEBUG: SHOW WORKDIR =================
        # result = subprocess.run(
        #     [
        #         self.config.executable,
        #         *self.config.global_args,
        #         "exec",
        #         *self.config.exec_args,
        #         #"--writable",
        #         "--pwd", "/testbed",
        #         str(self.sandbox_dir),
        #         "bash",
        #         "-c",
        #         "echo '=== DEBUG: CURRENT DIR ==='; pwd; ls; echo '==========================='"
        #     ],
        #     #stdout=subprocess.PIPE,
        #     #stderr=subprocess.STDOUT,
        #     text=True,
        #     capture_output=True,
        # )
        # print(result.stdout)
        
        # # ================= DELETE TEST FILES (ONCE) =================
        # if not self.cleaned_tests:
        #     print("RUNNING TEST CLEANUP")

        #     cleanup_cmd = (
        #         "echo '=== BEFORE TEST CLEANUP ==='; "
        #         "find . -name '*test*.py' | head -20; "
        #         "echo 'Removing test files...'; "
        #         "find . -type f -iname '*test*.py' -delete; "
        #         "ls sympy/core/tests/;"
        #         "echo '=== AFTER TEST CLEANUP ==='; "
        #         "find . -name '*test*.py' | head -20;"
        #     )

        #     result = subprocess.run(
        #         [
        #             self.config.executable,
        #             *self.config.global_args,
        #             "exec",
        #             *self.config.exec_args,
        #             #"--writable",
        #             "--pwd", "/testbed",
        #             str(self.sandbox_dir),
        #             "bash",
        #             "-c",
        #             cleanup_cmd,
        #         ],
        #         #stdout=subprocess.PIPE,
        #         #stderr=subprocess.STDOUT,
        #         text=True,
        #         capture_output=True,
        #     )

        #     print(result.stdout)

        #     self.cleaned_tests = True

        

        cmd = [self.config.executable, *self.config.global_args, "exec", *self.config.exec_args]

        work_dir = cwd or self.config.cwd
        if work_dir and work_dir != "/":
            cmd.extend(["--pwd", work_dir])

        for key in self.config.forward_env:
            if (value := os.getenv(key)) is not None:
                cmd.extend(["--env", f"{key}={value}"])
        for key, value in self.config.env.items():
            cmd.extend(["--env", f"{key}={value}"])

        #removed "--writable",

        cmd.extend([str(self.sandbox_dir), "bash", "-c", command])

        try:
            result = subprocess.run(
                cmd,
                text=True,
                timeout=timeout or self.config.timeout,
                encoding="utf-8",
                errors="replace",
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            output = {"output": result.stdout, "returncode": result.returncode, "exception_info": ""}
        except Exception as e:
            raw_output = getattr(e, "output", None)
            raw_output = (
                raw_output.decode("utf-8", errors="replace") if isinstance(raw_output, bytes) else (raw_output or "")
            )
            output = {
                "output": raw_output,
                "returncode": -1,
                "exception_info": f"An error occurred while executing the command: {e}",
                "extra": {"exception_type": type(e).__name__, "exception": str(e)},
            }
        self._check_finished(output)

        # ================= RUN NEW TESTS AFTER PATCH =================
        if "COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT" in output.get("output", ""):
            print("=== RUNNING NEWLY GENERATED TESTS ===")

            test_cmd = (
                "echo 'Running pytest on generated tests...'; "
                "pytest -q || echo 'Pytest failed'"
            )

            subprocess.run(
                [
                    self.config.executable,
                    *self.config.global_args,
                    "exec",
                    *self.config.exec_args,
                    #"--writable",
                    str(self.sandbox_dir),
                    "bash",
                    "-c",
                    test_cmd,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
        return output

    def _check_finished(self, output: dict):
        """Raises Submitted if the output indicates task completion."""
        lines = output.get("output", "").lstrip().splitlines(keepends=True)
        if lines and lines[0].strip() == "COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT" and output["returncode"] == 0:
            submission = "".join(lines[1:])
            raise Submitted(
                {
                    "role": "exit",
                    "content": submission,
                    "extra": {"exit_status": "Submitted", "submission": submission},
                }
            )

    def cleanup(self):
        shutil.rmtree(self.sandbox_dir, ignore_errors=True)

    def __del__(self):
        """Cleanup sandbox when object is destroyed."""
        self.cleanup()
        
