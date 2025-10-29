from __future__ import annotations
import json
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.rule import Rule
from rich.syntax import Syntax
from rich.markup import escape
from .analysis import Report
from .utils import iso_to_dt, duration_ms, human_ms


console = Console()


def render_report(r: Report, use_ai: bool = False):
    dur_ms = duration_ms(iso_to_dt(r.run.started_at), iso_to_dt(r.run.updated_at))
    dur = human_ms(dur_ms)
    baseline = human_ms(r.baseline_p50_ms) if r.baseline_p50_ms else "n/a"
    if r.baseline_p50_ms:
        pct = (dur_ms / r.baseline_p50_ms - 1.0) * 100.0
        delta = ("↑" if pct >= 0 else "↓") + f" {abs(pct):.0f}% vs median {baseline}"
    else:
        delta = "n/a"

    header = f"[bold]🧩 Job:[/bold] {r.workflow_name}  (run #{r.run.id} on [italic]{r.run.branch}[/])\n" \
             f"[bold]🚦 Status:[/bold] {r.run.conclusion or r.run.status}  (attempt {r.run.run_attempt})\n" \
             f"[bold]🕒 Duration:[/bold] {dur}  ({delta})\n" \
             f"[bold]🔁 Triggered by:[/bold] {r.run.event}  ({r.run.actor or 'unknown'})"
    console.print(Panel.fit(header))

    # If cancelled, surface best-effort reason
    if (r.run.conclusion or "").lower() == "cancelled" and r.cancellation_reason:
        console.print(f"[bold]🛑 Cancel reason:[/bold] {r.cancellation_reason}")

    if r.last_success:
        console.print(f"[bold]🟢 Last success:[/bold] run #{r.last_success.id} ({r.last_success.web_url})")
    else:
        console.print("[bold]🟡 Last success:[/bold] none found in sample window")

    if r.compare:
        files = r.compare.files or []
        names = ", ".join(f.get("filename", "") for f in files[:5]) + ("…" if len(files) > 5 else "")
        console.print(f"[bold]📦 Since last success ({r.compare.total_commits} commits):[/bold] {names or 'no file changes'}")
    console.print(Rule())

    if r.failing_jobs:
        console.print(f"[bold]🧪 Failing jobs:[/bold] {len(r.failing_jobs)}")
    else:
        console.print("[bold]🧪 Failing jobs:[/bold] not detected")

    # Display log excerpts for all failing jobs
    for i, job in enumerate(r.failing_jobs):
        # Find the failing step for this job
        failing_step = None
        for step in (job.steps or []):
            if (step.get("conclusion") or "").lower() in {"failure", "failed", "cancelled"}:
                failing_step = step
                break
        
        step_name = failing_step.get("name") if failing_step else None
        step_text = f" → step '{step_name}'" if step_name else ""
        
        console.print(Rule())
        console.print(f"[bold]📋 Failing Job {i+1}: {job.name}{step_text}[/bold]")
        
        if job.log_lines:
            # Highlight error lines
            error_patterns = ['error', 'Error', 'ERROR', 'failed', 'Failed', 'FAILED', 'fatal', 'Fatal', 'FATAL', 
                              'Exception', 'Traceback', 'assertion failed', 'AssertionError']
            
            highlighted_lines = []
            for line in job.log_lines:
                # Escape rich markup in log lines to prevent conflicts
                escaped_line = escape(line)
                is_error = any(pattern in line for pattern in error_patterns)
                if is_error:
                    highlighted_lines.append(f"[red]{escaped_line}[/red]")
                else:
                    highlighted_lines.append(escaped_line)
            
            # Join and display
            log_text = "\n".join(highlighted_lines)
            
            # Display in a panel
            console.print(Panel(log_text, title=f"Logs for {job.name}", border_style="red", expand=False))

    if r.suspects:
        if r.failing_jobs:
            console.print()  # Add spacing
        tbl = Table(title="💡 Suspects")
        tbl.add_column("Potential cause", overflow="fold")
        for s in r.suspects:
            tbl.add_row(s)
        console.print(tbl)


def report_to_json(r: Report) -> str:
    payload = {
        "run": {
            "id": r.run.id,
            "provider": r.run.provider,
            "repo": r.run.repo,
            "branch": r.run.branch,
            "event": r.run.event,
            "actor": r.run.actor,
            "status": r.run.status,
            "conclusion": r.run.conclusion,
            "run_attempt": r.run.run_attempt,
            "started_at": r.run.started_at,
            "updated_at": r.run.updated_at,
            "head_sha": r.run.head_sha,
            "web_url": r.run.web_url,
            "workflow_id": r.run.workflow_id,
        },
        "workflow_name": r.workflow_name,
        "cancellation_reason": r.cancellation_reason,
        "failing_jobs": [
            {
                "id": job.id,
                "name": job.name,
                "conclusion": job.conclusion,
                "started_at": job.started_at,
                "completed_at": job.completed_at,
                "steps": job.steps,
                "log_lines": job.log_lines if hasattr(job, 'log_lines') else None,
            }
            for job in r.failing_jobs
        ] if r.failing_jobs else [],
        "baseline_p50_ms": r.baseline_p50_ms,
        "last_success": (r.last_success.__dict__ if r.last_success else None),
        "compare": {
            "total_commits": r.compare.total_commits,
            "files": r.compare.files,
        } if r.compare else None,
        "suspects": r.suspects,
        "logs_path": str(r.logs_path) if r.logs_path else None,
    }
    return json.dumps(payload, indent=2)


