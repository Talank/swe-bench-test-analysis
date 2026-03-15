#!/usr/bin/env python3
"""
Exaple: python make_aug_patch.py --patch ../existing_prompt_results/20250522_tools_claude-4-opus/logs/astropy__astropy-13398/patch.diff --traj ../existing_prompt_results/20250522_tools_claude-4-opus/trajs/astropy__astropy-13398.txt -o aug_astropy__astropy-13398.diff
make_aug_patch.py
=================
Produces aug_patch.diff from a SWE-bench patch.diff + trajectory file.

  aug_patch.diff = patch.diff (100% verbatim)
                 + any test files/content the agent created during its
                   exploration that did NOT make it into the final patch

The logic is intentionally simple:

  1. Parse patch.diff  → collect (repo-path, added-lines) for every file.
  2. Parse trajectory  → collect every test-related file the agent
                         created or str_replace-edited, in order.
  3. For each trajectory test item:
       a. If the file path is NOT in the patch at all   → add full file diff
       b. If the file IS in the patch but the trajectory
          added MORE content than the patch kept         → add the delta
  4. Write: patch.diff text + the extra diff blocks

No pytest conversion. No scratchpad classification. Test files go in as-is.

Usage:
    python make_aug_patch.py --patch patch.diff --traj trajectory.txt
    python make_aug_patch.py --patch patch.diff --traj traj.txt -o aug.diff -v
    python make_aug_patch.py --patch patch.diff --traj traj.txt --debug
"""

import argparse
import json
import os
import re
import sys
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _norm_path(raw: str) -> str:
    """Strip /testbed/, ./, a/, b/ prefixes to get a repo-relative path."""
    p = raw.strip()
    for prefix in ("/testbed/", "./", "a/", "b/"):
        if p.startswith(prefix):
            p = p[len(prefix):]
    return p


def _is_test_path(path: str) -> bool:
    name = Path(path).name
    return (
        name.startswith("test_")
        or name.endswith("_test.py")
        or "/tests/" in path
        or "/test/" in path
    )


def _make_new_file_diff(repo_path: str, content: str) -> str:
    """Build a unified diff block that creates a new file."""
    lines = content.splitlines()
    n = len(lines)
    parts = [
        f"diff --git a/{repo_path} b/{repo_path}",
        "new file mode 100644",
        "index 0000000..0000001 100644",
        "--- /dev/null",
        f"+++ b/{repo_path}",
        f"@@ -0,0 +1,{n} @@",
    ]
    for line in lines:
        parts.append("+" + line)
    return "\n".join(parts)


def _make_append_diff(repo_path: str, new_lines: list[str],
                      after_line: int) -> str:
    """
    Build a unified diff hunk that appends new_lines after line `after_line`
    of an existing file.
    """
    n = len(new_lines)
    parts = [
        f"diff --git a/{repo_path} b/{repo_path}",
        f"index 0000000..0000001 100644",
        f"--- a/{repo_path}",
        f"+++ b/{repo_path}",
        f"@@ -{after_line},0 +{after_line + 1},{n} @@",
    ]
    for line in new_lines:
        parts.append("+" + line)
    return "\n".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# Patch parser
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PatchBlock:
    repo_path: str
    raw_text: str
    added_lines: list[str]    # lines added (without leading +)
    is_new_file: bool = False


class PatchParser:
    def parse(self, text: str) -> list[PatchBlock]:
        raw_blocks = re.split(r'(?=^diff --git )', text, flags=re.MULTILINE)
        result = []
        for block in raw_blocks:
            block = block.strip()
            if not block:
                continue
            m = re.match(r"diff --git a/(.+?) b/(.+)", block)
            if not m:
                continue
            repo_path = _norm_path(m.group(2))
            is_new = "new file mode" in block
            added = [
                line[1:]
                for line in block.splitlines()
                if line.startswith("+") and not line.startswith("+++")
            ]
            result.append(PatchBlock(
                repo_path=repo_path,
                raw_text=block,
                added_lines=added,
                is_new_file=is_new,
            ))
        return result


# ─────────────────────────────────────────────────────────────────────────────
# Trajectory parser
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TrajItem:
    raw_path: str
    repo_path: str
    operation: str      # "create" | "str_replace"
    content: str        # full content (create) or new_str (str_replace)
    old_str: str = ""
    new_str: str = ""


class TrajectoryParser:
    """
    Parses SWE-agent XML-style tool calls to collect test-related file ops.

    Handles:
      <invoke name="str_replace_based_edit_tool">
        <parameter name="command">create</parameter>
        <parameter name="path">...</parameter>
        <parameter name="file_text">...</parameter>
      </invoke>

      <invoke name="str_replace_based_edit_tool">
        <parameter name="command">str_replace</parameter>
        <parameter name="path">...</parameter>
        <parameter name="old_str">...</parameter>
        <parameter name="new_str">...</parameter>
      </invoke>
    """

    _BLOCK_RE = re.compile(r"<function_calls>(.*?)</function_calls>", re.DOTALL)
    _PARAM_RE = re.compile(r'<parameter name="([^"]+)">(.*?)</parameter>', re.DOTALL)
    _INVOKE_RE = re.compile(r'<invoke name="([^"]+)">')

    def parse(self, text: str) -> list[TrajItem]:
        items: list[TrajItem] = []
        seen: set[str] = set()

        for bm in self._BLOCK_RE.finditer(text):
            block = bm.group(1)

            params: dict[str, str] = {
                m.group(1): m.group(2)
                for m in self._PARAM_RE.finditer(block)
            }

            command = params.get("command", "")
            path    = params.get("path", "").strip()

            if not path:
                continue

            repo = _norm_path(path)

            # Only care about test-related files
            if not _is_test_path(repo):
                continue

            # ── create ────────────────────────────────────────────────────
            if command == "create":
                content = params.get("file_text", "")
                key = f"create:{repo}"
                if key not in seen:
                    seen.add(key)
                    items.append(TrajItem(
                        raw_path=path, repo_path=repo,
                        operation="create", content=content,
                    ))

            # ── str_replace ───────────────────────────────────────────────
            elif command == "str_replace":
                new_str = params.get("new_str", "")
                old_str = params.get("old_str", "")
                if not new_str.strip():
                    continue
                key = f"str_replace:{repo}:{hash(old_str)}"
                if key not in seen:
                    seen.add(key)
                    items.append(TrajItem(
                        raw_path=path, repo_path=repo,
                        operation="str_replace",
                        content=new_str,
                        old_str=old_str,
                        new_str=new_str,
                    ))

        return items


# ─────────────────────────────────────────────────────────────────────────────
# Coverage checker
# ─────────────────────────────────────────────────────────────────────────────

class CoverageChecker:
    """
    Decides whether each trajectory item is already fully covered by the patch.

    For "create" items:
      Covered iff the patch adds the same file with substantially the same content.

    For "str_replace" items:
      Covered iff every non-blank line in new_str appears in the patch's additions
      for that file.
    """

    def __init__(self, patch_blocks: list[PatchBlock]):
        self._by_path: dict[str, PatchBlock] = {b.repo_path: b for b in patch_blocks}

    def coverage(self, item: TrajItem) -> tuple[bool, str]:
        """Returns (is_covered, reason)."""
        pb = self._by_path.get(item.repo_path)

        if item.operation == "create":
            if pb is None:
                return False, "file not in patch at all"
            # The patch has this file in some form — the patch is the final,
            # authoritative version. The trajectory version is an intermediate
            # draft. Consider it covered.
            return True, f"file present in patch (+{len(pb.added_lines)} lines)"

        elif item.operation == "str_replace":
            if pb is None:
                return False, "file not in patch"
            # Check if the new_str lines are in the patch additions
            patch_added = set(pb.added_lines)
            traj_lines  = [l for l in item.new_str.splitlines() if l.strip()]
            if not traj_lines:
                return True, "new_str is empty"
            missing = [l for l in traj_lines if l not in patch_added]
            if not missing:
                return True, f"all {len(traj_lines)} new_str lines in patch"
            pct = int(100 * (len(traj_lines) - len(missing)) / len(traj_lines))
            return False, f"{len(missing)}/{len(traj_lines)} lines missing ({pct}% in patch)"

        return False, "unknown operation"

    @staticmethod
    def _content_subset(traj_content: str, patch_content: str) -> bool:
        def norm(s):
            return re.sub(r"\s+", " ", s).strip()
        nt = norm(traj_content)
        np = norm(patch_content)
        return nt == np or nt in np or np in nt


# ─────────────────────────────────────────────────────────────────────────────
# Delta extractor
# ─────────────────────────────────────────────────────────────────────────────

class DeltaExtractor:
    """
    For a trajectory item NOT fully covered by the patch,
    returns the content that should be added.
    """

    def __init__(self, patch_blocks: list[PatchBlock]):
        self._by_path: dict[str, PatchBlock] = {b.repo_path: b for b in patch_blocks}

    def missing_content(self, item: TrajItem) -> Optional[str]:
        if item.operation == "create":
            return item.content.strip() or None

        elif item.operation == "str_replace":
            pb = self._by_path.get(item.repo_path)
            new_str = item.new_str.strip()
            if not new_str:
                return None
            if pb is None:
                return new_str

            # Return only the lines NOT already in the patch
            patch_added_set = set(pb.added_lines)
            missing_lines = [
                l for l in item.new_str.splitlines()
                if l not in patch_added_set
            ]
            # If more than half is missing, return the whole new_str to keep context
            traj_lines = item.new_str.splitlines()
            if len(missing_lines) > len(traj_lines) * 0.5:
                return new_str
            return "\n".join(missing_lines).strip() or None

        return None


# ─────────────────────────────────────────────────────────────────────────────
# Assembler
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ExtraBlock:
    repo_path: str
    diff_text: str
    reason: str


class AugPatchAssembler:
    def build(self, original_patch_text: str, extra_blocks: list[ExtraBlock]) -> str:
        parts = [original_patch_text.rstrip()]
        for eb in extra_blocks:
            parts.append("")
            parts.append(eb.diff_text)
        return "\n".join(parts) + "\n"


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline
# ─────────────────────────────────────────────────────────────────────────────

class AugPatchPipeline:

    def __init__(self, verbose: bool = False, debug: bool = False):
        self.verbose = verbose
        self.debug   = debug

    def run(
        self,
        patch_path: str,
        traj_path: str,
        report_path: Optional[str],
        output_path: str,
    ) -> dict:
        log  = print if (self.verbose or self.debug) else lambda *a, **k: None
        dlog = print if self.debug else lambda *a, **k: None

        # ── 1. Load ───────────────────────────────────────────────────────────
        log("\n[1/5] Loading inputs ...")
        patch_text = Path(patch_path).read_text()
        traj_text  = Path(traj_path).read_text()

        if report_path:
            try:
                report = json.loads(Path(report_path).read_text())
                ftp = (report.get("tests_status", {})
                             .get("FAIL_TO_PASS", {})
                             .get("success", []))
                log(f"  report FAIL_TO_PASS: {ftp}")
            except Exception as e:
                log(f"  report.json parse error: {e}")

        # ── 2. Parse patch ────────────────────────────────────────────────────
        log("\n[2/5] Parsing patch.diff ...")
        patch_blocks = PatchParser().parse(patch_text)
        log(f"  {len(patch_blocks)} block(s):")
        for pb in patch_blocks:
            tag = "[test]" if _is_test_path(pb.repo_path) else "[src] "
            log(f"    {tag} {pb.repo_path}  (+{len(pb.added_lines)} lines"
                + ("  [new file]" if pb.is_new_file else "") + ")")

        # ── 3. Parse trajectory ───────────────────────────────────────────────
        log("\n[3/5] Parsing trajectory for test-related operations ...")
        traj_items = TrajectoryParser().parse(traj_text)
        log(f"  {len(traj_items)} test-related operation(s):")
        for ti in traj_items:
            log(f"    [{ti.operation:10s}] {ti.repo_path}  ({len(ti.content)} chars)")
            dlog(f"      content preview: {ti.content[:120]!r}")

        # ── 4. Coverage check ─────────────────────────────────────────────────
        log("\n[4/5] Checking coverage ...")
        checker   = CoverageChecker(patch_blocks)
        extractor = DeltaExtractor(patch_blocks)

        extra_blocks: list[ExtraBlock] = []
        seen_block_keys: set[str] = set()

        for ti in traj_items:
            covered, reason = checker.coverage(ti)
            status = "✓ covered" if covered else "✗ missing "
            log(f"  {status}  [{ti.operation:10s}] {ti.repo_path}")
            log(f"            {reason}")

            if covered:
                continue

            content = extractor.missing_content(ti)
            if not content:
                dlog(f"    → no content to add")
                continue

            # One block per (operation, path) — avoid duplicating whole files
            block_key = f"{ti.operation}:{ti.repo_path}"
            if block_key in seen_block_keys:
                dlog(f"    → already have a block for this key, skipping")
                continue
            seen_block_keys.add(block_key)

            if ti.operation == "create":
                diff_text = _make_new_file_diff(ti.repo_path, content)
                reason_str = f"trajectory created, not in patch"
            else:
                pb = next((b for b in patch_blocks if b.repo_path == ti.repo_path), None)
                after = len(pb.added_lines) + 80 if pb else 80
                diff_text = _make_append_diff(
                    ti.repo_path, content.splitlines(), after
                )
                reason_str = f"trajectory str_replace delta, not in patch"

            n_lines = len(content.splitlines())
            log(f"    → adding {n_lines} line(s) as new diff block")
            extra_blocks.append(ExtraBlock(ti.repo_path, diff_text, reason_str))

        # ── 5. Assemble ───────────────────────────────────────────────────────
        log(f"\n[5/5] Writing aug_patch.diff ...")
        aug_text = AugPatchAssembler().build(patch_text, extra_blocks)
        Path(output_path).write_text(aug_text)
        log(f"  Done: {output_path}")

        return {
            "patch_files": len(patch_blocks),
            "traj_test_items": len(traj_items),
            "covered_by_patch": len(traj_items) - len(extra_blocks),
            "extra_blocks_added": len(extra_blocks),
            "extra_paths": [eb.repo_path for eb in extra_blocks],
            "output_path": output_path,
        }


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="Augment a SWE-bench patch.diff with trajectory test artifacts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
        What it does:
          aug_patch.diff = patch.diff (verbatim, unchanged)
                         + diff blocks for any test files/edits the agent made
                           during exploration that were NOT kept in the final patch

        Examples:
          python make_aug_patch.py --patch patch.diff --traj traj.txt
          python make_aug_patch.py --patch patch.diff --traj traj.txt -v
          python make_aug_patch.py --patch patch.diff --traj traj.txt --debug
          python make_aug_patch.py --patch patch.diff --traj traj.txt --report report.json
        """),
    )
    ap.add_argument("--patch",   required=True, metavar="FILE")
    ap.add_argument("--traj",    required=True, metavar="FILE")
    ap.add_argument("--report",  default=None,  metavar="FILE")
    ap.add_argument("-o", "--output", default="aug_patch.diff", metavar="FILE")
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--debug",   action="store_true",
                    help="Per-item coverage detail (use when extra_blocks=0)")
    ap.add_argument("--summary", action="store_true")
    args = ap.parse_args()

    for p, label in [(args.patch, "--patch"), (args.traj, "--traj")]:
        if not Path(p).exists():
            ap.error(f"{label} not found: {p}")
    if args.report and not Path(args.report).exists():
        ap.error(f"--report not found: {args.report}")

    os.makedirs(os.path.join(os.getcwd(), "output"), exist_ok=True)

    pipeline = AugPatchPipeline(verbose=args.verbose, debug=args.debug)
    summary  = pipeline.run(
        patch_path=args.patch,
        traj_path=args.traj,
        report_path=args.report,
        output_path=os.path.join(os.getcwd(), "output", args.output)
    )

    if args.summary or args.verbose or args.debug:
        print("\n── Summary " + "─" * 48)
        print(json.dumps(summary, indent=2))

    if not (args.verbose or args.debug):
        added = summary["extra_blocks_added"]
        print(f"aug_patch.diff written to: {args.output}")
        print(f"  patch files          : {summary['patch_files']}")
        print(f"  traj test ops        : {summary['traj_test_items']}")
        print(f"  already in patch     : {summary['covered_by_patch']}")
        print(f"  extra blocks added   : {added}")
        for p in summary["extra_paths"]:
            print(f"    + {p}")
        if added == 0:
            if summary["traj_test_items"] == 0:
                print("\n  ℹ No test-related operations found in the trajectory.")
                print("    Re-run with --debug to see what the parser found.")
            else:
                print("\n  ℹ All trajectory test items were already in the patch.")
                print("    Re-run with --debug to see the per-item coverage check.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
