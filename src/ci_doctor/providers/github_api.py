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
    """
    Read-only GitHub API client for fetching GitHub Actions run data.
    
    SECURITY: This client ONLY performs GET requests. It cannot modify,
    create, update, or delete any repository data, workflows, or runs.
    """
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
        """
        Read-only GET request. This is the ONLY HTTP method used by this client.
        
        SECURITY: No POST, PUT, PATCH, or DELETE operations are performed.
        This ensures the tool cannot modify repositories, workflows, or runs.
        """
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


