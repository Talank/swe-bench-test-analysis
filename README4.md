# Pytest Coverage JSON Output
 
---
 
## 1. Coverage for AI-Generated Test Predictions + Developer Patch
 
### Goal
 
This version was created to evaluate AI-generated test patches from `preds.json` and compare their behavior:
 
- Before the developer fix
- After the developer fix from the dataset
The purpose is to check whether AI-generated tests:
 
- Execute relevant code
- Expose buggy behavior
- Validate the developer fix
---
 
### Files Modified
 
**Modified**
- `swebench/harness/test_spec/python.py`
- `swebench/harness/run_evaluation.py`


---
 
### Workflow
 
1. Load an AI-generated test patch from `preds.json`
2. Extract test directives from that patch
3. Run the selected test(s) **before** the developer fix
4. Collect coverage for the BEFORE run
5. Apply the dataset developer fix (patch) internally
6. Run the same test(s) again **after** the fix
7. Collect coverage for the AFTER run
8. Save parsed coverage results
---
 
### Changes in `python.py`
 
#### Added support for extracting test directives from AI-generated patches
Test directives are now derived from the AI-generated patch rather than the dataset `test_patch`.
 
#### Added BEFORE / AFTER execution phases
The eval script was extended to perform two runs:
- `BEFORE_FIX`
- `AFTER_FIX`
#### Added internal application of the developer patch
The dataset developer patch (`instance["patch"]`) is applied inside the eval script between the BEFORE and AFTER runs.
 
#### Added coverage collection
Coverage is collected during both runs using:
 
```bash
python -m coverage run -m pytest -q <test_directives>
python -m coverage json -o /tmp/<coverage_file>.json
```
 
#### Added output markers for parsing
The script prints coverage JSON between explicit markers:
 
```
=== BEFORE_COVERAGE_JSON_START ===
... JSON ...
=== BEFORE_COVERAGE_JSON_END ===
=== AFTER_COVERAGE_JSON_START ===
... JSON ...
=== AFTER_COVERAGE_JSON_END ===
```
 
#### Disabled shell tracing around JSON dumps
To avoid corrupting JSON output with shell trace lines, tracing is temporarily disabled around the `cat` commands:
 
```bash
set +x
cat /tmp/before_coverage.json
set -x
```
 
The same is done for the AFTER coverage block.
 
#### Added coverage installation
The evaluation environment was updated to install `coverage`.
 
---
 
### Changes in `run_evaluation.py`
 
#### Added extraction of BEFORE / AFTER coverage blocks
After `test_output.txt` is written, the harness extracts the raw coverage JSON blocks from the output using the marker strings.
 
#### Added safe JSON parsing
To handle extra shell or log text, parsing trims the extracted block to the first `{` and last `}` before calling `json.loads(...)`.
 
#### Added structured coverage output
A new file is written per instance: `coverage_metrics.json`
 
```json
{
 "before_fix_coverage_json": { ... },
 "after_fix_coverage_json": { ... }
}
```
 
---
 
### Output
 
Each evaluated instance can now produce:
- `test_output.txt`
- `coverage_metrics.json`
---
 


## 2. Coverage for Gold Patch Evaluation
 
### Goal
 
This version was created for SWE-bench's gold evaluation mode, where the dataset's gold patch is used during evaluation. This is separate from the AI-generated test workflow.
 
---
 
### Files Modified
 
**Modified**
- `swebench/harness/test_spec/python.py`
- `swebench/harness/run_evaluation.py`


---
 
### Workflow
 
This version supports evaluation with:
 
```bash
python -m swebench.harness.run_evaluation \
   --predictions_path gold \
   --max_workers 1 \
   --instance_ids <instance_id> \
   --run_id <run_id>
```
 
The goal is to collect coverage for the gold-patch workflow and compare behavior before and after the dataset developer fix.
 
---
 
### Changes in `python.py`
 
#### Added BEFORE / AFTER execution phases
The Python eval script was extended to support:
- `BEFORE_FIX`
- `AFTER_FIX`
#### Added application of the gold developer patch
The dataset developer fix (`instance["patch"]`) is applied inside the eval script between the two runs.
 
#### Added coverage collection
Coverage is collected for both BEFORE and AFTER runs using:
 
```bash
python -m coverage run -m pytest -q <test_directives>
python -m coverage json -o /tmp/<coverage_file>.json
```
 
#### Added coverage markers
The script prints raw JSON blocks between markers:
 
```
=== BEFORE_COVERAGE_JSON_START ===
... JSON ...
=== BEFORE_COVERAGE_JSON_END ===
=== AFTER_COVERAGE_JSON_START ===
... JSON ...
=== AFTER_COVERAGE_JSON_END ===
```
 
#### Disabled shell tracing around raw JSON output
Shell tracing is temporarily turned off while printing the coverage JSON so the parser receives clean JSON.
 
#### Added coverage installation
The evaluation environment installs `coverage` so the coverage commands run successfully.
 
---
 
### Changes in `run_evaluation.py`
 
#### Added extraction of coverage blocks from `test_output.txt`
The harness extracts the BEFORE and AFTER coverage JSON blocks after evaluation completes.
 
#### Added robust JSON parsing
Parsing trims to the actual JSON object before loading it.
 
#### Added structured output file
Coverage is saved to `coverage_metrics.json` with content like:
 
```json
{
 "before_fix_coverage_json": { ... },
 "after_fix_coverage_json": { ... }
}
```
 
---
 
### Output
 
Each evaluated instance can now produce:
- `test_output.txt`
- `coverage_metrics.json`
---
 
## Notes
 
### Coverage Scope
Even when only one test file is run, the coverage report is not limited to that file. It includes all Python files executed during that run.
 
### Difference Between the Two Versions
 
**AI-generated test version**
- Starts from an AI-created patch in `preds.json`
- Extracts test directives from that patch
- Applies the dataset developer patch internally
- Compares BEFORE vs AFTER behavior of AI-generated tests
**Gold evaluation version**
- Runs through SWE-bench's gold evaluation path
- Uses the dataset's gold or developer patch workflow
- Collects coverage around that process
- Compares BEFORE vs AFTER behavior in gold mode
 

