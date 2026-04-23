# Changes to Support Before/After Developer-Fix Evaluation of AI-Generated Tests
 
## Goal
 
The goal of these changes was to make the harness:
 
1. Apply the AI-generated test patch
2. Run the generated test on the buggy/base version
3. Apply the developer fix patch
4. Run the same generated test again on the fixed version
5. Capture the before/after behavior of the AI-generated test
---
 
## `swebench/harness/test_spec/python.py`
 
This is the main file where the evaluation script logic was changed.
 
### What Changed
 
- `get_test_directives(...)` was changed to derive test directives from the AI-generated prediction patch instead of the dataset `test_patch`
- `make_eval_script_list_py(...)` was changed so it now:
 - Builds the test command from the AI-generated patch
 - Runs the generated test before the developer fix
 - Applies the developer gold patch from `instance["patch"]`
 - Runs the same generated test after the fix
 - Prints `BEFORE_STATUS` and `AFTER_STATUS` markers


### Why This Mattered
 
Before this change, the harness was built around the dataset's developer test patch. After this change, it evaluates the AI-generated tests before and after applying the developer fix.
 
---
 
## `swebench/harness/run_evaluation.py`
 
This is where the harness was changed so it applies the AI-generated patch first and then runs the new eval script.
 
### What Changed
 
- The model prediction patch is written to `patch.diff`
- That patch is copied into the container
- The harness tries to apply it with `git apply` / `patch`
- `eval.sh` is created from the modified test spec
- `eval.sh` is run and its output is written to `test_output.txt`
### Why This Mattered
 
This is what made the harness actually run the AI-generated test patch and then execute the before-fix / after-fix logic produced by `python.py`.
 
---
 
## `swebench/harness/test_spec/create_scripts.py`
 
This file was changed so the eval-script creation layer forwards the prediction patch instead of the dataset test patch.
 
### What Changed
 
Changed from:
 
```python
def make_eval_script_list(
   instance, specs, env_name, repo_directory, base_commit, test_patch
) -> list:
```
 
to:
 
```python
def make_eval_script_list(
   instance, specs, env_name, repo_directory, base_commit, prediction_patch
) -> list:
```
 
And changed:
 
```python
return func(instance, specs, env_name, repo_directory, base_commit, test_patch)
```
 
to:
 
```python
return func(instance, specs, env_name, repo_directory, base_commit, prediction_patch)
```
 
### Why This Mattered
 
This file is the bridge between `test_spec.py` and the language-specific script generator. Changing it ensured the AI-generated patch was forwarded down into the script-generation logic.
 
---
 
## `swebench/harness/test_spec/test_spec.py`
 
This file was changed so `make_test_spec(...)` takes the prediction patch and passes it into eval-script generation.
 
### What Changed
 
Changed from:
 
```python
def make_test_spec(
   instance: SWEbenchInstance,
   namespace: Optional[str] = None,
   ...
)
```
 
to:
 
```python
def make_test_spec(
   instance: SWEbenchInstance,
   prediction_patch: str,
   namespace: Optional[str] = None,
   ...
)
```
 
Also removed:
 
```python
test_patch = instance["test_patch"]
```
 
And changed:
 
```python
eval_script_list = make_eval_script_list(
   instance, specs, env_name, repo_directory, base_commit, test_patch
)
```
 
to:
 
```python
eval_script_list = make_eval_script_list(
   instance, specs, env_name, repo_directory, base_commit, prediction_patch
)
```
 
### Why This Mattered
 
This reconnects test-spec generation to the AI-generated patch instead of the stored developer `test_patch`, so the eval script is built for the generated tests.
 
---
 
## `swebench/harness/grading.py`
 
This file was changed to add custom grading logic for the two-phase before/after evaluation.
 
### What Changed
 
Added a custom helper `get_two_phase_status(...)` which:
 
- Reads the test log
- Checks for bad codes like patch/apply/reset/test errors
- Extracts:
 - `BEFORE_STATUS=...`
 - `AFTER_STATUS=...`
- Computes:
 - `before_failed`
 - `after_passed`
Then in the report generation logic, instead of using the original SWE-bench grading flow, the code was changed to:
 
- Call `get_two_phase_status(test_log_path)`
- Mark the patch as resolved if `before_failed and after_passed`
- Store `tests_status` as:
```python
{
   "before_failed": before_failed,
   "after_passed": after_passed,
}
```
 
### What This Replaced
 
This replaced the original logic that:
 
- Parsed logs with `get_logs_eval(...)`
- Built an `eval_ref` using `FAIL_TO_PASS` and `PASS_TO_PASS`
- Called `get_eval_tests_report(...)`
- Used the standard SWE-bench resolution logic


### Why This Mattered
 
This made grading depend directly on the AI-generated test's two-phase behavior — fail before the developer fix, pass after the developer fix — instead of the standard SWE-bench F2P/P2P grading path.
 
---
 
## Summary of the Overall Effect
 
Together, these changes made the harness support a workflow where:
 
1. The AI-generated patch is treated as the patch to apply
2. The generated tests are extracted from that patch
3. The same generated tests are run on the buggy version
4. The developer gold patch is then applied
5. The same generated tests are run again on the fixed version
6. Grading is based on whether the generated test:
  - Fails before the fix
  - Passes after the fix
---
 
## Files Changed
 
- `swebench/harness/run_evaluation.py`
- `swebench/harness/test_spec/python.py`
- `swebench/harness/test_spec/create_scripts.py`
- `swebench/harness/test_spec/test_spec.py`
- `swebench/harness/grading.py`



