import argparse
import io
import json
import re
import tarfile
import tempfile
from pathlib import Path

import docker


DEFAULT_CONTAINER_ID = "0f3f8ecdc93d"
DEFAULT_JSON_FILE = "/home/tbaral/research/llm_test_analysis_project/swe-bench-test-analysis/traj_files3/preds.json"


def _exec(container, command, workdir="/testbed"):
    return container.exec_run(["bash", "-lc", command], workdir=workdir)


def _decode(output):
    if isinstance(output, bytes):
        return output.decode(errors="replace")
    return str(output)


def _container_python(container):
    result = _exec(container, "python --version")
    if result.exit_code == 0:
        return "python"
    return "python3"


def _top_level_package(path):
    parts = Path(path).parts
    if not parts:
        return "."
    return parts[0]


def _ensure_dir_in_container(container, path):
    _exec(container, f"mkdir -p {path}")


def _put_text_file(container, root_dir, relative_path, content):
    data = content.encode()
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w") as tar:
        info = tarfile.TarInfo(name=relative_path)
        info.size = len(data)
        info.mode = 0o644
        tar.addfile(info, io.BytesIO(data))
    archive.seek(0)
    container.put_archive(root_dir, archive.read())


def _remove_container_path(container, path):
    _exec(container, f"rm -rf {path}")


def _extract_new_file_texts(patch_str):
    new_files = {}
    current_path = None
    current_lines = []
    collecting = False
    is_new_file = False

    def flush():
        nonlocal current_path, current_lines, collecting, is_new_file
        if current_path and is_new_file and current_lines:
            new_files[current_path] = "\n".join(current_lines).rstrip("\n") + "\n"
        current_path = None
        current_lines = []
        collecting = False
        is_new_file = False

    for line in patch_str.splitlines():
        if line.startswith("diff --git "):
            flush()
            match = re.match(r"^diff --git a/(.+?) b/(.+?)$", line)
            if match:
                current_path = match.group(2)
            continue

        if line.startswith("new file mode "):
            is_new_file = True
            continue

        if line.startswith("@@"):
            collecting = True
            continue

        if collecting and current_path and is_new_file and line.startswith("+") and not line.startswith("+++"):
            current_lines.append(line[1:])

    flush()
    return new_files


def get_modified_files(patch_str):
    """Return source files and test files referenced by a git diff."""
    files = re.findall(r"^[+-]{3} [ab]/(.*)$", patch_str, re.MULTILINE)
    source_files = []
    test_files = []

    for file_path in set(files):
        if file_path == "dev/null":
            continue
        if "test" in file_path or file_path.endswith("_test.py"):
            test_files.append(file_path)
        else:
            source_files.append(file_path)

    return source_files, test_files


def _build_test_targets(container, test_files, new_file_texts, instance_id, pre_patch):
    targets = []
    temp_root = "/testbed"

    for test_file in test_files:
        if pre_patch and test_file in new_file_texts:
            destination = f"{temp_root}/{test_file}"
            _ensure_dir_in_container(container, str(Path(destination).parent))
            _put_text_file(container, temp_root, test_file, new_file_texts[test_file])
            targets.append(destination)
        else:
            targets.append(f"/testbed/{test_file}")

    return targets


def infer_mutation_targets(source_files, test_files):
    if source_files:
        return sorted({_top_level_package(path) for path in source_files})

    inferred = set()
    for test_file in test_files:
        inferred.add(_top_level_package(test_file))

    return sorted(inferred) or ["."]


def _read_coverage_summary(container, coverage_json_path, label):
    result = _exec(container, f"cat {coverage_json_path}")
    if result.exit_code != 0:
        return f"[{label}] Unable to read coverage JSON at {coverage_json_path}"

    payload = _decode(result.output).strip()
    if not payload:
        return f"[{label}] Empty coverage JSON at {coverage_json_path}"

    data = json.loads(payload)
    totals = data.get("totals", {})
    percent = totals.get("percent_covered")
    covered_lines = totals.get("covered_lines")
    num_statements = totals.get("num_statements")
    if percent is None:
        return f"[{label}] Coverage JSON collected"

    return f"[{label}] Coverage: {percent:.2f}% ({covered_lines}/{num_statements} lines covered)"


def _read_mutmut_summary(output, label):
    text = _decode(output).strip()
    if not text:
        return f"[{label}] Empty mutmut output"

    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    summary = lines[-10:] if len(lines) > 10 else lines
    return f"[{label}] Mutation results:\n" + "\n".join(summary)


def _ensure_container_tool(container, module_name):
    python_cmd = _container_python(container)
    check = _exec(container, f'{python_cmd} -c "import {module_name}"')
    if check.exit_code == 0:
        return

    install = _exec(container, f"{python_cmd} -m pip install --quiet {module_name}")
    if install.exit_code != 0:
        raise RuntimeError(_decode(install.output))


def _ensure_container_dependencies(container):
    for module_name in ("coverage", "mutmut"):
        _ensure_container_tool(container, module_name)


def _write_mutmut_config(container, mutation_targets):
    config_text = "[mutmut]\npaths_to_mutate = " + ",".join(mutation_targets) + "\n"
    _put_text_file(container, "/testbed", "setup.cfg", config_text)


def run_evaluation(container, label, source_files, test_files, new_file_texts, instance_id):
    print(f"\n--- Running {label} Evaluation ---")

    mutation_targets = infer_mutation_targets(source_files, test_files)
    test_targets = _build_test_targets(container, test_files, new_file_texts, instance_id, pre_patch=(label == "PRE-PATCH"))
    coverage_summary = None
    mutation_summary = None

    print(f"[{label}] Mutation targets: {mutation_targets}")
    if test_targets:
        print(f"[{label}] Test targets: {test_targets}")
    else:
        print(f"[{label}] No test files identified in patch to run coverage.")

    if test_targets:
        python_cmd = _container_python(container)
        coverage_json_path = f"/tmp/{label.lower().replace('-', '_')}_coverage.json"
        _exec(container, f"{python_cmd} -m coverage erase")
        coverage_cmd = f"PYTHONPATH=/testbed {python_cmd} -m coverage run -m pytest -q {' '.join(test_targets)}"
        print(f"[{label}] Executing Coverage: {coverage_cmd}")
        coverage_result = _exec(container, coverage_cmd)
        print(_decode(coverage_result.output))

        json_result = _exec(container, f"PYTHONPATH=/testbed {python_cmd} -m coverage json -o {coverage_json_path}")
        if json_result.exit_code == 0:
            coverage_summary = _read_coverage_summary(container, coverage_json_path, label)
            print(coverage_summary)
        else:
            coverage_summary = _decode(json_result.output)
            print(coverage_summary)

    python_cmd = _container_python(container)
    _write_mutmut_config(container, mutation_targets)
    mutmut_cmd = f"PYTHONPATH=/testbed {python_cmd} -m mutmut run"
    print(f"[{label}] Executing Mutation on: {','.join(mutation_targets)}")
    mutmut_result = _exec(container, mutmut_cmd)
    if mutmut_result.exit_code != 0:
        print(_decode(mutmut_result.output))

    try:
        results_result = _exec(container, f"PYTHONPATH=/testbed {python_cmd} -m mutmut results")
        mutation_summary = _read_mutmut_summary(results_result.output, label)
        print(mutation_summary)
    finally:
        _remove_container_path(container, "/testbed/setup.cfg")

    return {
        "label": label,
        "coverage_summary": coverage_summary,
        "mutation_summary": mutation_summary,
    }


def apply_patch_to_container(container, patch_str):
    print("--- Applying Patch ---")
    _ensure_dir_in_container(container, "/tmp/patch_eval")

    with tempfile.NamedTemporaryFile("w", suffix=".diff", delete=False) as host_patch:
        host_patch.write(patch_str)
        host_patch_path = host_patch.name

    try:
        patch_bytes = Path(host_patch_path).read_bytes()
        archive = io.BytesIO()
        with tarfile.open(fileobj=archive, mode="w") as tar:
            info = tarfile.TarInfo(name="patch.diff")
            info.size = len(patch_bytes)
            info.mode = 0o644
            tar.addfile(info, io.BytesIO(patch_bytes))
        archive.seek(0)
        container.put_archive("/tmp/patch_eval", archive.read())

        result = _exec(container, "git apply --whitespace=nowarn /tmp/patch_eval/patch.diff")
        if result.exit_code != 0:
            print("Error applying patch:", _decode(result.output))
        return result.exit_code == 0
    finally:
        Path(host_patch_path).unlink(missing_ok=True)


def main(container_id, json_path, instance_id=None):
    client = docker.from_env()
    container = client.containers.get(container_id)
    _ensure_container_dependencies(container)

    with open(json_path, "r") as handle:
        data = json.load(handle)

    if instance_id is None:
        instance_id = next(iter(data))
        print(f"No instance id supplied; using {instance_id}")
    elif instance_id not in data:
        raise KeyError(f"Instance {instance_id} not found in {json_path}")

    patch_text = data[instance_id].get("model_patch", "")
    if not patch_text:
        print(f"No patch found for {instance_id}")
        return

    source_files, test_files = get_modified_files(patch_text)
    new_file_texts = _extract_new_file_texts(patch_text)

    print(f"Detected Source Files: {source_files}")
    print(f"Detected Test Files: {test_files}")
    if new_file_texts:
        print(f"Detected New Files: {sorted(new_file_texts)}")

    temp_repo_tests = [f"/testbed/{path}" for path in test_files if path in new_file_texts]

    try:
        before_result = run_evaluation(container, "PRE-PATCH", source_files, test_files, new_file_texts, instance_id)

        for temp_test_path in temp_repo_tests:
            _remove_container_path(container, temp_test_path)

        if apply_patch_to_container(container, patch_text):
            after_result = run_evaluation(container, "POST-PATCH", source_files, test_files, new_file_texts, instance_id)
            print("\n=== FINAL SUMMARY ===")
            print(before_result.get("coverage_summary") or "[PRE-PATCH] Coverage: unavailable")
            print(before_result.get("mutation_summary") or "[PRE-PATCH] Mutation results: unavailable")
            print(after_result.get("coverage_summary") or "[POST-PATCH] Coverage: unavailable")
            print(after_result.get("mutation_summary") or "[POST-PATCH] Mutation results: unavailable")
        else:
            print("Evaluation aborted: Patch application failed.")
    finally:
        for temp_test_path in temp_repo_tests:
            _remove_container_path(container, temp_test_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate a patch inside a running container.")
    parser.add_argument("--container-id", default=DEFAULT_CONTAINER_ID)
    parser.add_argument("--json-file", default=DEFAULT_JSON_FILE)
    parser.add_argument("--instance-id", default=None)
    args = parser.parse_args()

    main(args.container_id, args.json_file, args.instance_id)