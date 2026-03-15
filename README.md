# swe-bench-test-analysis

Run the following command for testing of the make_aug_patch.py script:

```
cd scripts
python make_aug_patch.py --patch ../existing_prompt_results/20250522_tools_claude-4-opus/logs/astropy__astropy-13398/patch.diff --traj ../existing_prompt_results/20250522_tools_claude-4-opus/trajs/astropy__astropy-13398.txt -o aug_astropy__astropy-13398.diff -v
```

The summary output of the script should look like this:

```
{
  "patch_files": 10,
  "traj_test_items": 0,
  "covered_by_patch": 0,
  "extra_blocks_added": 0,
  "extra_paths": [],
  "output_path": "/home/tbaral/research/llm_test_analysis_project/swe-bench-test-analysis/swe-bench-test-analysis/scripts/output/aug_astropy__astropy-13398.diff"
}
```

If the `extra_blocks_added` is more than 0, then the generated patch is augmented with extra blocks. Which means there was some extra tests in the trajectory that were not in the original patch. The augmented patch will be saved to `output/aug_astropy__astropy-13398.diff`. You can then apply this patch to the codebase and run the tests to see if it passes.

@ToDo:
1. Run the script on the whole dataset. Find the ones that has tests in intermediate steps. Analyze the generated patches. Basically we are interested in finding the cases where `extra_blocks_added` is more than 0.

Run the below command for the batch run, it will also generate a csv with results for the extra blocks (instances_with_extra_blocks.csv):

python3 patch_batch.py --csv ../swebench_lite_test.csv --patch-root ../existing_prompt_results/20250522_tools_claude-4-opus/logs --traj-root ../existing_prompt_results/20250522_tools_claude-4-opus/trajs -v
