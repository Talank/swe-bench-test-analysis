#!/bin/bash
set -uxo pipefail
source /opt/miniconda3/bin/activate
conda activate testbed
cd /testbed
git config --global --add safe.directory /testbed
cd /testbed
git status
git show
git -c core.fileMode=false diff a3e2897bfaf9eaac1d6649da535c4e721c89fa69
source /opt/miniconda3/bin/activate
conda activate testbed
python -m pip install -e .
git checkout a3e2897bfaf9eaac1d6649da535c4e721c89fa69 lib/matplotlib/tests/test_axes.py
git apply -v - <<'EOF_114329324912'
diff --git a/lib/matplotlib/tests/test_axes.py b/lib/matplotlib/tests/test_axes.py
--- a/lib/matplotlib/tests/test_axes.py
+++ b/lib/matplotlib/tests/test_axes.py
@@ -6369,3 +6369,10 @@ def test_hist_nan_data():
 
     assert np.allclose(bins, nanbins)
     assert np.allclose(edges, nanedges)
+
+
+def test_hist_range_and_density():
+    _, bins, _ = plt.hist(np.random.rand(10), "auto",
+                          range=(0, 1), density=True)
+    assert bins[0] == 0
+    assert bins[-1] == 1

EOF_114329324912
echo '=== BEFORE_FIX ==='
BEFORE_STATUS=0
echo '>>>>> Start Test Output'
pytest -rA lib/matplotlib/tests/test_axes.py >/tmp/before_test_output.log 2>&1 || BEFORE_STATUS=$?
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
python -m pytest -q lib/matplotlib/tests/test_axes.py >/tmp/before_cov_run.log 2>&1 || BEFORE_COV_STATUS=$?
python -m coverage run -m pytest -q lib/matplotlib/tests/test_axes.py >/tmp/before_cov_pytest.log 2>&1 || true
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
diff --git a/lib/matplotlib/axes/_axes.py b/lib/matplotlib/axes/_axes.py
--- a/lib/matplotlib/axes/_axes.py
+++ b/lib/matplotlib/axes/_axes.py
@@ -6686,7 +6686,7 @@ def hist(self, x, bins=None, range=None, density=None, weights=None,
 
         density = bool(density) or bool(normed)
         if density and not stacked:
-            hist_kwargs = dict(density=density)
+            hist_kwargs['density'] = density
 
         # List to store all the top coordinates of the histograms
         tops = []

EOF_114329324912
echo '=== AFTER_FIX ==='
AFTER_STATUS=0
echo '>>>>> Start Test Output'
pytest -rA lib/matplotlib/tests/test_axes.py >/tmp/after_test_output.log 2>&1 || AFTER_STATUS=$?
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
python -m pytest -q lib/matplotlib/tests/test_axes.py >/tmp/after_cov_run.log 2>&1 || AFTER_COV_STATUS=$?
python -m coverage run -m pytest -q lib/matplotlib/tests/test_axes.py >/tmp/after_cov_pytest.log 2>&1 || true
python -m coverage json -o /tmp/after_coverage.json || true
echo AFTER_COV_STATUS=$AFTER_COV_STATUS
echo '=== AFTER_COVERAGE_JSON_START ==='
set +x
cat /tmp/after_coverage.json 2>/dev/null || true
set -x
echo
echo '=== AFTER_COVERAGE_JSON_END ==='
git checkout a3e2897bfaf9eaac1d6649da535c4e721c89fa69 lib/matplotlib/tests/test_axes.py
