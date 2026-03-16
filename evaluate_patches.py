import os
import csv
import subprocess
from pathlib import Path

CSV_FILE = "swebench_lite_test.csv"
PATCH_ROOT = "existing_prompt_results/20250522_tools_claude-4-opus/logs"
WORKDIR = "repos"

RESULT_CSV = "coverage_mutation_results.csv"


def run(cmd, cwd=None):
    print("\n$", cmd)
    subprocess.run(cmd, shell=True, check=True, cwd=cwd)


def clone_repo(repo_url, repo_dir):

    if not Path(repo_dir).exists():
        run(f"git clone {repo_url} {repo_dir}")


def reset_repo(repo_dir):

    run("git reset --hard", cwd=repo_dir)
    run("git clean -fd", cwd=repo_dir)


def apply_patch(repo_dir, patch_file):

    run(f"git apply {patch_file}", cwd=repo_dir)


def install_dependencies(repo_dir):

    run("pip install pytest pytest-cov coverage mutmut", cwd=repo_dir)

    if Path(repo_dir, "requirements.txt").exists():
        run("pip install -r requirements.txt", cwd=repo_dir)


def run_coverage(repo_dir):

    run(
        "pytest --cov=. --cov-report=term --cov-report=xml",
        cwd=repo_dir,
    )

    coverage_file = Path(repo_dir) / "coverage.xml"

    if coverage_file.exists():
        return "coverage.xml"
    return None


def run_mutation(repo_dir):

    try:
        run("mutmut run", cwd=repo_dir)

        result = subprocess.run(
            "mutmut results",
            shell=True,
            capture_output=True,
            text=True,
            cwd=repo_dir,
        )

        return result.stdout.strip()

    except Exception:
        return "mutation_failed"


def main():

    os.makedirs(WORKDIR, exist_ok=True)

    results = []

    with open(CSV_FILE) as f:

        reader = csv.DictReader(f)

        for row in reader:

            instance_id = row["instance_id"]
            repo = row["repo"]
            base_commit = row["base_commit"]

            repo_url = f"https://github.com/{repo}.git"

            patch_dir = Path(PATCH_ROOT) / instance_id
            patch_file = patch_dir / "patch.diff"

            if not patch_file.exists():
                print("Skipping (no patch):", instance_id)
                continue

            repo_dir = Path(WORKDIR) / repo.split("/")[-1]

            print("\n===============================")
            print("Processing:", instance_id)

            clone_repo(repo_url, repo_dir)

            reset_repo(repo_dir)

            run(f"git checkout {base_commit}", cwd=repo_dir)

            apply_patch(repo_dir, patch_file)

            install_dependencies(repo_dir)

            coverage = run_coverage(repo_dir)

            mutation = run_mutation(repo_dir)

            results.append(
                {
                    "instance_id": instance_id,
                    "coverage_file": coverage,
                    "mutation_result": mutation,
                }
            )

    with open(RESULT_CSV, "w", newline="") as f:

        writer = csv.DictWriter(
            f,
            fieldnames=["instance_id", "coverage_file", "mutation_result"],
        )

        writer.writeheader()
        writer.writerows(results)

    print("\nSaved results to", RESULT_CSV)


if __name__ == "__main__":
    main()


