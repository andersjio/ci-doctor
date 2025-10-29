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
    log_lines: List[str] | None = None  # Extracted log lines for this job


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
    async def extract_logs_for_job(self, *, logs_zip: bytes, job: JobMeta) -> List[str] | None: ...


