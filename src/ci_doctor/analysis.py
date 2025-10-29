from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Dict, Any
import sys
from .providers.base import BaseProvider, RunMeta, JobMeta, CompareMeta
from .utils import iso_to_dt, duration_ms, median_ms, extract_failing_step_logs


@dataclass
class Report:
    run: RunMeta
    workflow_name: str
    failing_jobs: List[JobMeta]  # All failing jobs
    baseline_p50_ms: Optional[int]
    last_success: Optional[RunMeta]
    compare: Optional[CompareMeta]
    suspects: List[str]
    logs_path: Optional[Path]
    # Present when run.conclusion == "cancelled"; best-effort heuristic
    cancellation_reason: Optional[str] = None


def pick_failing_jobs(jobs: List[JobMeta]) -> List[JobMeta]:
    """Return all failing jobs."""
    failing = []
    for j in jobs:
        if (j.conclusion or "").lower() in {"failure", "failed", "cancelled"}:
            failing.append(j)
    return failing


def gen_suspects(run: RunMeta, jobs: List[JobMeta], cmp: Optional[CompareMeta], baseline_p50_ms: Optional[int]) -> List[str]:
    suspects: List[str] = []
    # Duration spike
    if baseline_p50_ms:
        dur = duration_ms(iso_to_dt(run.started_at), iso_to_dt(run.updated_at))
        if dur > baseline_p50_ms * 1.5:
            suspects.append("Duration spike vs median → cache miss, dependency install, or external service slowdown.")
    # Lockfile / deps
    if cmp:
        filenames = [f.get("filename", "") for f in (cmp.files or [])]
        lock_suffixes = ["package-lock.json","yarn.lock","pnpm-lock.yaml","poetry.lock","requirements.txt","Pipfile.lock","go.sum","Cargo.lock"]
        if any(name.endswith(s) for name in filenames for s in lock_suffixes):
            suspects.append("Dependency/lockfile changes may have broken build or invalidated caches.")
        wf_names = [".github/workflows/", "ci.yml", "ci.yaml", ".github/workflows/ci.yaml", ".github/workflows/ci.yml"]
        if any(any(seg in name for seg in wf_names) for name in filenames):
            suspects.append("Workflow changes detected → runner image, permissions, or cache keys altered.")
        if any(name.lower().endswith(("dockerfile", ".dockerfile")) for name in filenames):
            suspects.append("Dockerfile changes → base image/layer differences causing failures.")
    if run.event in {"workflow_dispatch", "repository_dispatch"}:
        suspects.append("Manual/dispatch trigger → verify inputs/secrets.")
    return suspects[:3]


async def analyze(provider: BaseProvider, *, run_url: str, sample_limit: int = 50, want_logs: bool = False, save_logs_dir: Optional[Path] = None) -> Report:
    # 1) fetch run, jobs, workflow
    run = await provider.get_run(run_url=run_url)
    jobs = await provider.list_run_jobs(run=run)
    wf_name = await provider.get_workflow_name(run=run)
    failing_jobs = pick_failing_jobs(jobs)

    # 2) successes for baseline + last success
    successes = await provider.list_successful_runs(run=run, limit=sample_limit)
    # last success before this run
    cur_start = iso_to_dt(run.started_at)
    last_success: Optional[RunMeta] = None
    durations: List[int] = []
    for r in successes:
        durations.append(duration_ms(iso_to_dt(r.started_at), iso_to_dt(r.updated_at)))
        if iso_to_dt(r.started_at) < cur_start and not last_success:
            last_success = r
    baseline_p50 = median_ms(durations) if durations else None

    # 3) compare
    cmp = await provider.compare_since_last_success(current=run, last_success=last_success)

    # 4) logs - automatically fetch for failing builds
    logs_path: Optional[Path] = None
    
    # Download logs if build failed or explicitly requested
    is_failed = (run.conclusion or "").lower() in {"failure", "failed", "cancelled"}
    cancellation_reason: Optional[str] = None
    if is_failed or want_logs:
        try:
            blob = await provider.download_logs_zip(run=run)
            
            
            # Extract logs for all failing jobs
            if is_failed and failing_jobs:
                for job in failing_jobs:
                    # Find the failing step for this job
                    failing_step = None
                    for step in (job.steps or []):
                        if (step.get("conclusion") or "").lower() in {"failure", "failed", "cancelled"}:
                            failing_step = step
                            break
                    
                    failing_step_name = failing_step.get("name") if failing_step else None
                    job.log_lines = extract_failing_step_logs(blob, job.name, failing_step_name, max_lines=50)

            # Best-effort cancellation reason inference
            if (run.conclusion or "").lower() == "cancelled":
                # Heuristics:
                # 1) If any job failed (not cancelled), cancellation likely followed a failure elsewhere
                any_failure = any((j.conclusion or "").lower() in {"failure", "failed"} for j in jobs)
                any_cancel = any((j.conclusion or "").lower() == "cancelled" for j in jobs)
                if any_failure and any_cancel:
                    cancellation_reason = "Cancelled after a failure in another job"
                else:
                    # 2) Look for common log phrases
                    text_snippets: List[str] = []
                    for j in failing_jobs:
                        if j.log_lines:
                            text_snippets.extend(j.log_lines)
                    joined = "\n".join(text_snippets).lower()
                    if "timeout" in joined or "timed out" in joined:
                        cancellation_reason = "Timeout reached"
                    elif "the operation was canceled" in joined or "the operation was cancelled" in joined:
                        cancellation_reason = "Operation canceled (manual, concurrency, or timeout)"
                    else:
                        cancellation_reason = None
            
            # Save to disk if explicitly requested (via --save-logs flag)
            if save_logs_dir:
                save_logs_dir.mkdir(parents=True, exist_ok=True)
                path = save_logs_dir / f"run-{run.id}-logs.zip"
                path.write_bytes(blob)
                logs_path = path
        except Exception as e:
            # Log the error for debugging but don't fail the whole analysis
            print(f"Warning: Could not extract logs: {e}", file=sys.stderr)

    # 5) suspects
    suspects = gen_suspects(run, jobs, cmp, baseline_p50)

    return Report(
        run=run,
        workflow_name=wf_name,
        failing_jobs=failing_jobs,
        baseline_p50_ms=baseline_p50,
        last_success=last_success,
        compare=cmp,
        suspects=suspects,
        logs_path=logs_path,
        cancellation_reason=cancellation_reason,
    )


