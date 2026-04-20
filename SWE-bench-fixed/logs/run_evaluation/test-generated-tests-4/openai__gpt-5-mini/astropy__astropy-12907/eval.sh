#!/bin/bash
set -uxo pipefail
source /opt/miniconda3/bin/activate
conda activate testbed
cd /testbed
git config --global --add safe.directory /testbed
cd /testbed
git status
git show
git -c core.fileMode=false diff d16bfe05a744909de4b27f5875fe0d4ed41ce607
source /opt/miniconda3/bin/activate
conda activate testbed
python -m pip install -e .[test] --verbose
echo '=== BEFORE_FIX ==='
BEFORE_STATUS=0
: '>>>>> Start Test Output'
pytest -rA astropy/modeling/tests/test_separable_nested.py || BEFORE_STATUS=$?
: '>>>>> End Test Output'
echo BEFORE_STATUS=$BEFORE_STATUS
echo '=== APPLY_GOLD_PATCH ==='
git apply -v - <<'EOF_114329324912'
diff --git a/astropy/modeling/separable.py b/astropy/modeling/separable.py
--- a/astropy/modeling/separable.py
+++ b/astropy/modeling/separable.py
@@ -242,7 +242,7 @@ def _cstack(left, right):
         cright = _coord_matrix(right, 'right', noutp)
     else:
         cright = np.zeros((noutp, right.shape[1]))
-        cright[-right.shape[0]:, -right.shape[1]:] = 1
+        cright[-right.shape[0]:, -right.shape[1]:] = right
 
     return np.hstack([cleft, cright])
 

EOF_114329324912
echo '=== AFTER_FIX ==='
AFTER_STATUS=0
: '>>>>> Start Test Output'
pytest -rA astropy/modeling/tests/test_separable_nested.py || AFTER_STATUS=$?
: '>>>>> End Test Output'
echo AFTER_STATUS=$AFTER_STATUS
