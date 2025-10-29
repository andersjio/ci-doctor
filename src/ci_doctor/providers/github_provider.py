from __future__ import annotations
from typing import List, Dict, Any, Optional
from .base import BaseProvider, RunMeta, JobMeta, CompareMeta
from .github_api import GitHubClient
from ..utils import parse_github_run_url


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
        return [JobMeta(id=str(j.id), name=j.name, conclusion=j.conclusion, started_at=j.started_at, completed_at=j.completed_at, steps=j.steps, log_lines=None) for j in jobs]

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


