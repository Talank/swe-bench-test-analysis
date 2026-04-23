1. Inside mini-swe-agent-fixed, run the below command to generate 'preds.json' - the patch with the test file:

`mini-extra swebench-single --subset verified --split test --model openai/gpt-5-mini -i astropy__astropy-12907 -y -o ../traj_files/astropy__astropy-12907.json`

(Look inside traj_files folder for 'preds.json', also 'astropy__astropy-12907.json' is the trajectory file)

2. Inside SWE-bench-fixed, run the below command to use the preds.json file with the modified SWE bench harness to evaluate the test on buggy and fixed version, and get coverage as well:

`python3 -m swebench.harness.run_evaluation --dataset_name princeton-nlp/SWE-bench_Verified --predictions_path ../traj_files/preds.json --max_workers 1  --run_id test-generated-tests-1 --instance_ids astropy__astropy-12907`

(Look inside SWE-bench-fixed/logs/test-generated-tests-1 for results. 'test_output.txt' has log and coverage_metrics.json has coverage info.)

3. Insidde SWE-bench, run the below command to evaluate and get coverage of the developer given test on developer fixed version:

`python -m swebench.harness.run_evaluation --predictions_path gold --max_workers 1 --instance_ids astropy__astropy-12907  --run_id validate-gold-covg`

(Look inside SWE-bench/logs/validate-gold-covg for results. 'test_output.txt' has log and coverage_metrics.json has coverage info.)