# Cursor Instructions — Build the “CI Doctor” CLI (Python + Typer)

**Goal:** Implement a lean, stateless-by-default CLI called **ci-doctor** that analyzes a **GitHub Actions run URL** and prints a compact diagnosis (status, failing step, last success, duration vs baseline, trigger, changed files, suspects). The CLI must be designed so we can later add providers for **Jenkins** and **Azure DevOps** without large refactors.

## High-level requirements

* Language: **Python 3.11+**
* CLI framework: **Typer**
* HTTP client: **httpx** (async)
* Output: human-friendly (default, using `rich`) + **JSON** (`--format json`)
* Auth: GitHub **Personal Access Token** (env `GITHUB_TOKEN`) or `--token` flag.
* Stateless-by-default. No DB. Optional small in-memory/ETag cache for the process lifetime.
* Flags: `--ai`, `--save-logs`, `--no-cache/--cache`, `--max-samples`, `--timeout`, `--format {pretty,json}`
* Scope v0: **GitHub-only**. Ship an abstraction for future **Jenkins**/**Azure DevOps** providers.

## Repository layout

```
ci-doctor/
  pyproject.toml
  README.md
  LICENSE
  .env.example
  .gitignore
  src/
    ci_doctor/
      __init__.py
      cli.py               # Typer app entrypoint
      analysis.py          # orchestration + heuristics + provider-agnostic logic
      render.py            # rich/pretty output + JSON serializer
      utils.py             # url parsing, math, time helpers
      providers/
        __init__.py
        base.py            # Base provider protocol / abstract class
        github_api.py      # Thin GitHub REST client
        github_provider.py # Implements Base provider for GitHub
        # jenkins_provider.py (stub later)
        # azure_provider.py (stub later)
  tests/
    test_url_parse.py
    test_utils.py
  requirements.txt         # if we don’t use PEP 621 deps in pyproject
  Makefile                 # convenience targets
```

## Dependencies

Add these to `pyproject.toml` (PEP 621) **or** `requirements.txt`.

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "ci-doctor"
version = "0.1.0"
description = "CLI to diagnose CI pipeline runs (GitHub first)"
authors = [{ name = "Anders", email = "dev@example.com" }]
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
  "typer==0.12.5",
  "httpx==0.27.2",
  "pydantic==2.9.2",
  "rich==13.9.2",
  "python-dotenv==1.0.1",
]

[project.scripts]
ci-doctor = "ci_doctor.cli:main"
```

**If using `requirements.txt`:**

```txt
typer==0.12.5
httpx==0.27.2
pydantic==2.9.2
rich==13.9.2
python-dotenv==1.0.1
```

## Makefile (convenience)

```makefile
.PHONY: fmt lint test run

run:
	python -m ci_doctor.cli analyze $(URL)

fmt:
	python -m pip install ruff black
	ruff check --fix src
	black src tests

lint:
	ruff check src

test:
	pytest -q
```

## .env.example

```bash
# Copy to .env and set your token or pass --token
GITHUB_TOKEN=ghp_xxx
```

## Provider Abstraction

Create a narrow provider interface so later Jenkins/Azure can plug in transparently.

`src/ci_doctor/providers/base.py`

```python
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol

@dataclass
class RunMeta:
    id: str
    provider: str  # "github" | "jenkins" | "azure"
    repo: str      # provider-specific repo identifier
    branch: str
    event: str
    actor: str | None
    status: str
    conclusion: str | None
    run_attempt: int
    started_at: str
    updated_at: str
    head_sha: str | None
    web_url: str
    workflow_id: str | None

@dataclass
class JobMeta:
    id: str
    name: str
    conclusion: str | None
    started_at: str | None
    completed_at: str | None
    steps: List[Dict[str, Any]]

@dataclass
class CompareMeta:
    total_commits: int
    files: List[Dict[str, Any]]

class BaseProvider(Protocol):
    async def get_run(self, *, run_url: str) -> RunMeta: ...
    async def list_run_jobs(self, *, run: RunMeta) -> List[JobMeta]: ...
    async def get_workflow_name(self, *, run: RunMeta) -> str: ...
    async def list_successful_runs(self, *, run: RunMeta, limit: int) -> List[RunMeta]: ...
    async def compare_since_last_success(self, *, current: RunMeta, last_success: RunMeta | None) -> CompareMeta | None: ...
    async def download_logs_zip(self, *, run: RunMeta) -> bytes: ...
```

## GitHub provider

`src/ci_doctor/providers/github_api.py`

```python
from __future__ import annotations
import httpx
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

class GitHubAuthError(Exception): ...
class GitHubAPIError(Exception): ...

@dataclass
class GHRun:
    id: int
    status: str
    conclusion: Optional[str]
    event: str
    run_attempt: int
    run_started_at: str
    updated_at: str
    head_branch: str
    head_sha: str
    actor_login: Optional[str]
    workflow_id: int
    html_url: str
    owner: str
    repo: str

@dataclass
class GHJob:
    id: int
    name: str
    conclusion: Optional[str]
    started_at: str | None
    completed_at: str | None
    steps: List[Dict[str, Any]]

class GitHubClient:
    def __init__(self, token: str, api_base: str = "https://api.github.com", timeout: float = 10.0, use_cache: bool = False):
        self.client = httpx.AsyncClient(timeout=timeout, headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "ci-doctor/0.1",
        }, follow_redirects=True)
        self.api_base = api_base.rstrip("/")
        self.use_cache = use_cache
        self._etag: dict[str, str] = {}

    async def aclose(self):
        await self.client.aclose()

    async def _get(self, url: str, params: dict | None = None) -> httpx.Response:
        headers = {}
        if self.use_cache and url in self._etag:
            headers["If-None-Match"] = self._etag[url]
        r = await self.client.get(url, params=params or {}, headers=headers)
        if r.status_code == 401:
            raise GitHubAuthError("Unauthorized. Check token scopes (actions:read, contents:read).")
        if r.status_code >= 400 and r.status_code != 304:
            raise GitHubAPIError(f"GET {url} -> {r.status_code} {r.text}")
        if et := r.headers.get("ETag"):
            self._etag[url] = et
        return r

    async def get_run(self, owner: str, repo: str, run_id: int) -> GHRun:
        url = f"{self.api_base}/repos/{owner}/{repo}/actions/runs/{run_id}"
        r = await self._get(url)
        d = r.json()
        return GHRun(
            id=d["id"], status=d["status"], conclusion=d.get("conclusion"), event=d["event"],
            run_attempt=d.get("run_attempt", 1), run_started_at=d["run_started_at"], updated_at=d["updated_at"],
            head_branch=d["head_branch"], head_sha=d["head_sha"], actor_login=(d.get("actor") or {}).get("login"),
            workflow_id=d["workflow_id"], html_url=d["html_url"], owner=owner, repo=repo
        )

    async def list_jobs(self, owner: str, repo: str, run_id: int) -> List[GHJob]:
        url = f"{self.api_base}/repos/{owner}/{repo}/actions/runs/{run_id}/jobs"
        r = await self._get(url, params={"per_page": 100})
        jobs = []
        for j in r.json().get("jobs", []):
            jobs.append(GHJob(
                id=j["id"], name=j["name"], conclusion=j.get("conclusion"),
                started_at=j.get("started_at"), completed_at=j.get("completed_at"), steps=j.get("steps", [])
            ))
        return jobs

    async def get_workflow(self, owner: str, repo: str, workflow_id: int) -> dict:
        url = f"{self.api_base}/repos/{owner}/{repo}/actions/workflows/{workflow_id}"
        return (await self._get(url)).json()

    async def list_success(self, owner: str, repo: str, workflow_id: int, branch: str, per_page: int = 50, page: int = 1) -> dict:
        url = f"{self.api_base}/repos/{owner}/{repo}/actions/workflows/{workflow_id}/runs"
        return (await self._get(url, params={"branch": branch, "status": "success", "per_page": per_page, "page": page})).json()

    async def compare(self, owner: str, repo: str, base: str, head: str) -> dict:
        url = f"{self.api_base}/repos/{owner}/{repo}/compare/{base}...{head}"
        return (await self._get(url)).json()

    async def logs_zip(self, owner: str, repo: str, run_id: int) -> bytes:
        url = f"{self.api_base}/repos/{owner}/{repo}/actions/runs/{run_id}/logs"
        return (await self._get(url)).content
```

`src/ci_doctor/providers/github_provider.py`

```python
from __future__ import annotations
from typing import List, Dict, Any, Optional
from .base import BaseProvider, RunMeta, JobMeta, CompareMeta
from .github_api import GitHubClient, GHRun
from ..utils import parse_github_run_url, iso_to_dt

class GitHubProvider(BaseProvider):
    def __init__(self, token: str, api_base: str = "https://api.github.com", timeout: float = 10.0, use_cache: bool = False):
        self.gh = GitHubClient(token=token, api_base=api_base, timeout=timeout, use_cache=use_cache)

    async def close(self):
        await self.gh.aclose()

    async def get_run(self, *, run_url: str) -> RunMeta:
        parsed = parse_github_run_url(run_url)
        run = await self.gh.get_run(parsed.owner, parsed.repo, parsed.run_id)
        return RunMeta(
            id=str(run.id), provider="github", repo=f"{parsed.owner}/{parsed.repo}", branch=run.head_branch,
            event=run.event, actor=run.actor_login, status=run.status, conclusion=run.conclusion,
            run_attempt=run.run_attempt, started_at=run.run_started_at, updated_at=run.updated_at,
            head_sha=run.head_sha, web_url=run.html_url, workflow_id=str(run.workflow_id)
        )

    async def list_run_jobs(self, *, run: RunMeta) -> List[JobMeta]:
        owner, repo = run.repo.split("/")
        jobs = await self.gh.list_jobs(owner, repo, int(run.id))
        return [JobMeta(id=str(j.id), name=j.name, conclusion=j.conclusion, started_at=j.started_at, completed_at=j.completed_at, steps=j.steps) for j in jobs]

    async def get_workflow_name(self, *, run: RunMeta) -> str:
        owner, repo = run.repo.split("/")
        wf = await self.gh.get_workflow(owner, repo, int(run.workflow_id))
        return wf.get("name", f"workflow_{run.workflow_id}")

    async def list_successful_runs(self, *, run: RunMeta, limit: int) -> List[RunMeta]:
        owner, repo = run.repo.split("/")
        data = await self.gh.list_success(owner, repo, int(run.workflow_id), run.branch, per_page=min(limit, 50))
        out: List[RunMeta] = []
        for r in data.get("workflow_runs", []):
            out.append(RunMeta(
                id=str(r["id"]), provider="github", repo=f"{owner}/{repo}", branch=r["head_branch"],
                event=r["event"], actor=(r.get("actor") or {}).get("login"), status=r["status"],
                conclusion=r.get("conclusion"), run_attempt=r.get("run_attempt", 1),
                started_at=r["run_started_at"], updated_at=r["updated_at"], head_sha=r["head_sha"],
                web_url=r["html_url"], workflow_id=str(r["workflow_id"])
            ))
        return out

    async def compare_since_last_success(self, *, current: RunMeta, last_success: RunMeta | None) -> CompareMeta | None:
        if not last_success:
            return None
        owner, repo = current.repo.split("/")
        data = await self.gh.compare(owner, repo, last_success.head_sha, current.head_sha)  # type: ignore
        return CompareMeta(total_commits=data.get("total_commits", 0), files=data.get("files", []))

    async def download_logs_zip(self, *, run: RunMeta) -> bytes:
        owner, repo = run.repo.split("/")
        return await self.gh.logs_zip(owner, repo, int(run.id))
```

## Analysis & heuristics (provider-agnostic)

`src/ci_doctor/analysis.py`

```python
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Dict, Any
from .providers.base import BaseProvider, RunMeta, JobMeta, CompareMeta
from .utils import iso_to_dt, duration_ms, median_ms

@dataclass
class Report:
    run: RunMeta
    workflow_name: str
    failing_job: Optional[JobMeta]
    failing_step: Optional[Dict[str, Any]]
    baseline_p50_ms: Optional[int]
    last_success: Optional[RunMeta]
    compare: Optional[CompareMeta]
    suspects: List[str]
    logs_path: Optional[Path]

def pick_failing_job(jobs: List[JobMeta]) -> tuple[Optional[JobMeta], Optional[Dict[str, Any]]]:
    for j in jobs:
        if (j.conclusion or "").lower() in {"failure", "failed"}:
            for step in (j.steps or []):
                if (step.get("conclusion") or "").lower() in {"failure", "failed"}:
                    return j, step
            return j, None
    return None, None

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
    failing_job, failing_step = pick_failing_job(jobs)

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

    # 4) logs
    logs_path: Optional[Path] = None
    if want_logs:
        blob = await provider.download_logs_zip(run=run)
        if save_logs_dir:
            save_logs_dir.mkdir(parents=True, exist_ok=True)
            path = save_logs_dir / f"run-{run.id}-logs.zip"
            path.write_bytes(blob)
            logs_path = path

    # 5) suspects
    suspects = gen_suspects(run, jobs, cmp, baseline_p50)

    return Report(
        run=run,
        workflow_name=wf_name,
        failing_job=failing_job,
        failing_step=failing_step,
        baseline_p50_ms=baseline_p50,
        last_success=last_success,
        compare=cmp,
        suspects=suspects,
        logs_path=logs_path,
    )
```

## CLI entrypoint

`src/ci_doctor/cli.py`

```python
from __future__ import annotations
import asyncio, os
from pathlib import Path
import typer
from rich.console import Console
from dotenv import load_dotenv

from .analysis import analyze
from .render import render_report, report_to_json
from .providers.github_provider import GitHubProvider

app = typer.Typer(help="CI Doctor: analyze a CI run URL and get a diagnosis.")
console = Console()

DEFAULT_TIMEOUT = 10.0

@app.command("analyze")
def cmd_analyze(
    run_url: str = typer.Argument(..., help="GitHub Actions run URL"),
    token: str | None = typer.Option(None, "--token", help="GitHub token (or env GITHUB_TOKEN)"),
    ai: bool = typer.Option(False, "--ai", help="Enable AI suggestions (placeholder)"),
    save_logs: bool = typer.Option(False, "--save-logs", help="Download logs ZIP to ./artifacts"),
    no_cache: bool = typer.Option(True, "--no-cache/--cache", help="Disable conditional HTTP cache"),
    max_samples: int = typer.Option(50, "--max-samples", help="Max successful runs to sample for baseline"),
    timeout: float = typer.Option(DEFAULT_TIMEOUT, "--timeout", help="HTTP timeout seconds"),
    format_: str = typer.Option("pretty", "--format", help="pretty|json", case_sensitive=False),
):
    """Analyze a GitHub Actions run and print a compact diagnosis."""
    load_dotenv()
    gh_token = token or os.getenv("GITHUB_TOKEN")
    if not gh_token:
        console.print("[red]Missing GitHub token.[/red] Set --token or GITHUB_TOKEN env.")
        raise typer.Exit(code=10)

    provider = GitHubProvider(token=gh_token, timeout=timeout, use_cache=not no_cache)
    try:
        report = asyncio.run(
            analyze(provider, run_url=run_url, sample_limit=max_samples, want_logs=(save_logs or ai), save_logs_dir=Path("artifacts") if save_logs else None)
        )
    finally:
        asyncio.run(provider.close())

    if format_.lower() == "json":
        console.print(report_to_json(report))
    else:
        render_report(report, use_ai=ai)
        if ai:
            console.print("[yellow]AI suggestion placeholder:[/yellow] integrate LLM summarizer here (future).")


def main():
    app()

if __name__ == "__main__":
    main()
```

## Rendering

`src/ci_doctor/render.py`

```python
from __future__ import annotations
import json
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.rule import Rule
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

    if r.last_success:
        console.print(f"[bold]🟢 Last success:[/bold] run #{r.last_success.id} ({r.last_success.web_url})")
    else:
        console.print("[bold]🟡 Last success:[/bold] none found in sample window")

    if r.compare:
        files = r.compare.files or []
        names = ", ".join(f.get("filename", "") for f in files[:5]) + ("…" if len(files) > 5 else "")
        console.print(f"[bold]📦 Since last success ({r.compare.total_commits} commits):[/bold] {names or 'no file changes'}")
    console.print(Rule())

    if r.failing_job:
        step = r.failing_step.get("name") if r.failing_step else None
        console.print(f"[bold]🧪 Failing job:[/bold] {r.failing_job.name}" + (f" → step “{step}”" if step else ""))
    else:
        console.print("[bold]🧪 Failing job:[/bold] not detected")

    if r.suspects:
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
        "failing_job": (r.failing_job.__dict__ if r.failing_job else None),
        "failing_step": r.failing_step,
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
```

## Utilities

`src/ci_doctor/utils.py`

```python
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlparse

@dataclass
class ParsedRunURL:
    owner: str
    repo: str
    run_id: int

def parse_github_run_url(url: str) -> ParsedRunURL:
    u = urlparse(url)
    if u.netloc not in {"github.com", "www.github.com"}:
        raise ValueError("URL host is not github.com")
    parts = [p for p in u.path.split("/") if p]
    # /owner/repo/actions/runs/<id>
    if len(parts) < 5 or parts[2] != "actions" or parts[3] != "runs":
        raise ValueError("Not a GitHub Actions run URL")
    owner, repo, _, _, run_id = parts[:5]
    return ParsedRunURL(owner=owner, repo=repo, run_id=int(run_id))

def iso_to_dt(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))

def duration_ms(start: datetime, end: datetime) -> int:
    return int((end - start).total_seconds() * 1000)

def median_ms(values: list[int]) -> int:
    if not values:
        return 0
    xs = sorted(values)
    n = len(xs)
    return xs[n//2] if n % 2 == 1 else (xs[n//2 - 1] + xs[n//2]) // 2

def human_ms(ms: int | None) -> str:
    if ms is None:
        return "n/a"
    s = ms / 1000
    if s < 60:
        return f"{int(s)}s"
    m, s = divmod(int(s), 60)
    if m < 60:
        return f"{m}m{s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m"
```

## README.md (authoring brief)

* What it does (paste run URL → diagnosis)
* Install & usage
* Example output
* Provider architecture & how to add Jenkins later
* Security notes (stateless, read-only scopes)

**Usage snippet:**

```bash
# Install (editable dev)
pip install -e .
export GITHUB_TOKEN=ghp_...

# Run analysis
ci-doctor analyze https://github.com/owner/repo/actions/runs/123456789

# JSON output for bot integrations
ci-doctor analyze <url> --format json > report.json

# Save logs (ZIP) and enable AI placeholder
ci-doctor analyze <url> --save-logs --ai
```

## Tests (lightweight)

`tests/test_url_parse.py` and `tests/test_utils.py` — cover URL parsing and median/human duration helpers.

## Acceptance criteria (MVP)

* ✅ Parses a GitHub Actions run URL and fetches data using GitHub REST.
* ✅ Prints: status/conclusion, failing job/step, last success URL, duration vs P50 baseline, trigger/actor, top changed files, suspects.
* ✅ Supports flags: `--ai`, `--save-logs`, `--no-cache/--cache`, `--max-samples`, `--timeout`, `--format json`.
* ✅ Clean provider abstraction (GitHub today; Jenkins/Azure later) without touching CLI/analysis code.
* ✅ No persistent storage required; uses live API calls.

## Next steps (post-MVP, optional)

* Parse logs ZIP to extract ±N lines around failing step.
* Slack formatter (`--format slack`).
* Jenkins provider implementing `BaseProvider` with Jenkins JSON API.
* Azure DevOps provider (Builds, Timeline, Logs) implementing `BaseProvider`.
* Real `--ai` integration (LLM summarizer with compact prompt).
