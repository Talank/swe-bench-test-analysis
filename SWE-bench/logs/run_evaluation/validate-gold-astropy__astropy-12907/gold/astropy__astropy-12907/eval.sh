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
git checkout d16bfe05a744909de4b27f5875fe0d4ed41ce607 astropy/modeling/tests/test_separable.py
git apply -v - <<'EOF_114329324912'
diff --git a/astropy/modeling/tests/test_separable.py b/astropy/modeling/tests/test_separable.py
--- a/astropy/modeling/tests/test_separable.py
+++ b/astropy/modeling/tests/test_separable.py
@@ -28,6 +28,13 @@
 p1 = models.Polynomial1D(1, name='p1')
 
 
+cm_4d_expected = (np.array([False, False, True, True]),
+                  np.array([[True,  True,  False, False],
+                            [True,  True,  False, False],
+                            [False, False, True,  False],
+                            [False, False, False, True]]))
+
+
 compound_models = {
     'cm1': (map3 & sh1 | rot & sh1 | sh1 & sh2 & sh1,
             (np.array([False, False, True]),
@@ -52,7 +59,17 @@
     'cm7': (map2 | p2 & sh1,
             (np.array([False, True]),
              np.array([[True, False], [False, True]]))
-            )
+            ),
+    'cm8': (rot & (sh1 & sh2), cm_4d_expected),
+    'cm9': (rot & sh1 & sh2, cm_4d_expected),
+    'cm10': ((rot & sh1) & sh2, cm_4d_expected),
+    'cm11': (rot & sh1 & (scl1 & scl2),
+             (np.array([False, False, True, True, True]),
+              np.array([[True,  True,  False, False, False],
+                        [True,  True,  False, False, False],
+                        [False, False, True,  False, False],
+                        [False, False, False, True,  False],
+                        [False, False, False, False, True]]))),
 }
 
 

EOF_114329324912
echo '=== BEFORE_FIX ==='
BEFORE_STATUS=0
echo '>>>>> Start Test Output'
pytest -rA astropy/modeling/tests/test_separable.py >/tmp/before_test_output.log 2>&1 || BEFORE_STATUS=$?
echo '=== BEFORE_PYTEST_LOG_START ==='
set +x
cat /tmp/before_test_output.log 2>/dev/null || true
set -x
echo '=== BEFORE_PYTEST_LOG_END ==='
echo '>>>>> End Test Output'
echo BEFORE_STATUS=$BEFORE_STATUS
echo '=== BEFORE_COVERAGE ==='
python -m coverage erase || true
BEFORE_COV_STATUS=0
python -m pytest -q astropy/modeling/tests/test_separable.py >/tmp/before_cov_run.log 2>&1 || BEFORE_COV_STATUS=$?
python -m coverage run -m pytest -q astropy/modeling/tests/test_separable.py >/tmp/before_cov_pytest.log 2>&1 || true
python -m coverage json -o /tmp/before_coverage.json || true
echo BEFORE_COV_STATUS=$BEFORE_COV_STATUS
echo '=== BEFORE_COVERAGE_JSON_START ==='
set +x
cat /tmp/before_coverage.json 2>/dev/null || true
set -x
echo
echo '=== BEFORE_COVERAGE_JSON_END ==='
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
echo '>>>>> Start Test Output'
pytest -rA astropy/modeling/tests/test_separable.py >/tmp/after_test_output.log 2>&1 || AFTER_STATUS=$?
echo '=== AFTER_PYTEST_LOG_START ==='
set +x
cat /tmp/after_test_output.log 2>/dev/null || true
set -x
echo '=== AFTER_PYTEST_LOG_END ==='
echo '>>>>> End Test Output'
echo AFTER_STATUS=$AFTER_STATUS
echo '=== AFTER_COVERAGE ==='
python -m coverage erase || true
AFTER_COV_STATUS=0
python -m pytest -q astropy/modeling/tests/test_separable.py >/tmp/after_cov_run.log 2>&1 || AFTER_COV_STATUS=$?
python -m coverage run -m pytest -q astropy/modeling/tests/test_separable.py >/tmp/after_cov_pytest.log 2>&1 || true
python -m coverage json -o /tmp/after_coverage.json || true
echo AFTER_COV_STATUS=$AFTER_COV_STATUS
echo '=== AFTER_COVERAGE_JSON_START ==='
set +x
cat /tmp/after_coverage.json 2>/dev/null || true
set -x
echo
echo '=== AFTER_COVERAGE_JSON_END ==='
git checkout d16bfe05a744909de4b27f5875fe0d4ed41ce607 astropy/modeling/tests/test_separable.py
