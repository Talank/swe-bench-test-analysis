#!/bin/bash
set -uxo pipefail
source /opt/miniconda3/bin/activate
conda activate testbed
cd /testbed
git config --global --add safe.directory /testbed
cd /testbed
git status
git show
git -c core.fileMode=false diff 5e17a90c19f7eecfa10c1ab872648ae7e2131323
source /opt/miniconda3/bin/activate
conda activate testbed
python -m pip install -e .
: '>>>>> Start Test Output'
PYTHONWARNINGS='ignore::UserWarning,ignore::SyntaxWarning' bin/test -C --verbose sympy/core/tests/test_mod_regression.py
: '>>>>> End Test Output'
