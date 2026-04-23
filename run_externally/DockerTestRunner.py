import subprocess
import os
import sys

class DockerTestRunner:
    def __init__(self, container_name: str, testbed_path: str = "/testbed"):
        self.container_name = container_name
        self.testbed = testbed_path

    def _exec(self, command: str):
        """Helper to run commands inside the container."""
        full_command = [
            "docker", "exec", "-w", self.testbed, 
            self.container_name, "bash", "-c", command
        ]
        result = subprocess.run(full_command, capture_output=True, text=True)
        return result

    def apply_patch(self, patch_file_path: str):
        """Copies patch to container and applies it via git."""
        print(f"[*] Copying {patch_file_path} to container...")
        # Copy host file to container
        subprocess.run(["docker", "cp", patch_file_path, f"{self.container_name}:{self.testbed}/patch.txt"])
        
        print("[*] Applying patch...")
        # Use git apply for cleaner patching
        res = self._exec("git apply patch.txt")
        if res.returncode != 0:
            print(f"[!] Patch failed: {res.stderr}")
        return res.returncode == 0

    def run_coverage(self):
        """Runs pytest-cov and returns the percentage."""
        print("[*] Running Coverage...")
        # We use --cov=. to cover the whole project
        res = self._exec("pytest --cov=. --cov-report=term-missing")
        print(res.stdout)
        return res.stdout

    def run_mutation(self):
        """Runs mutmut. Note: Mutation testing can be very slow."""
        print("[*] Running Mutation Testing...")
        # Initialize mutmut if not already done
        self._exec("mutmut run")
        res = self._exec("mutmut results")
        print(res.stdout)
        return res.stdout

def get_swebench_docker_image_name(instance: dict) -> str:
    """Get the image name for a SWEBench instance."""
    image_name = instance.get("image_name", None) or instance.get("docker_image", None)
    if image_name is None:
        # Docker doesn't allow double underscore, so we replace them with a magic token
        iid = instance["instance_id"]
        id_docker_compatible = iid.replace("__", "_1776_")
        # image_name = f"docker.io/swebench/sweb.eval.x86_64.{id_docker_compatible}:latest".lower()
        image_name = f"swebench/sweb.eval.x86_64.{id_docker_compatible}:latest".lower()
        # print(f"container link: {image_name}")

    return image_name

# --- Execution Logic ---
if __name__ == "__main__":
    instance = sys.argv[1] # instance ID or name


    CONTAINER_NAME = get_swebench_docker_image_name({"instance_id": instance})

    runner = DockerTestRunner(CONTAINER_NAME)
    patch_file = f"patches/{instance}.patch"

    if runner.apply_patch("patch.txt"):
        coverage_output = runner.run_coverage()
        mutation_output = runner.run_mutation()
        
        print("\n--- FINAL REPORT ---")
        # Logic to parse outputs and calculate 'Optimal Scores' goes here
