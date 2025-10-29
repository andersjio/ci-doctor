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
    return xs[n // 2] if n % 2 == 1 else (xs[n // 2 - 1] + xs[n // 2]) // 2


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


def extract_failing_step_logs(logs_zip: bytes, failing_job_name: str, failing_step_name: str | None, max_lines: int = 50, context_lines: int = 5) -> list[str] | None:
    """
    Extract log lines from GitHub Actions logs ZIP for a failing step.
    
    Smart extraction: Finds error/failure lines and returns context around them.
    If no errors found, returns the last max_lines.
    
    Returns list of log lines with context, or None if not found.
    """
    import sys
    import zipfile
    import io
    import re
    
    try:
        with zipfile.ZipFile(io.BytesIO(logs_zip), 'r') as zip_ref:
            # GitHub Actions can have two structures:
            # 1. Flat structure: files like "1_Step name.txt" at root
            # 2. Nested structure: files in folders like "123_Job/1_Step name.txt"
            
            log_file = None
            
            # Try to find the log file by matching step name
            if failing_step_name:
                # Try flat structure first (most common for simple workflows)
                # Look for files like "1_Step name.txt"
                step_pattern = re.compile(rf'^\d+_{re.escape(failing_step_name)}.txt$', re.IGNORECASE)
                for name in zip_ref.namelist():
                    # Check if it's a flat structure file
                    if '/' not in name and step_pattern.match(name):
                        log_file = name
                        break
                    
                    # Check if it's in a nested structure
                    parts = name.split('/')
                    if len(parts) == 2 and step_pattern.match(parts[1]):
                        log_file = name
                        break
                
                # If no exact match, try partial match
                if not log_file:
                    for name in zip_ref.namelist():
                        if failing_step_name.lower() in name.lower() and name.endswith('.txt'):
                            log_file = name
                            break
            
            # If still no match and we have a job name, try to find by job name
            if not log_file and failing_job_name:
                # Try exact match first with regex
                job_pattern = re.compile(rf'^\d+_{re.escape(failing_job_name)}.txt$', re.IGNORECASE)
                for name in zip_ref.namelist():
                    # Check flat or nested
                    basename = name.split('/')[-1] if '/' in name else name
                    if job_pattern.match(basename):
                        log_file = name
                        break
                
                # If no exact match, try partial match
                if not log_file:
                    job_pattern = re.compile(rf'^\d+_{re.escape(failing_job_name.replace(" ", "_"))}', re.IGNORECASE)
                    for name in zip_ref.namelist():
                        basename = name.split('/')[-1] if '/' in name else name
                        if job_pattern.match(basename) and name.endswith('.txt') and 'system' not in name.lower():
                            log_file = name
                            break
            
            if not log_file:
                return None
            
            # Read the log file
            log_content = zip_ref.read(log_file).decode('utf-8', errors='replace')
            
            lines = log_content.splitlines()
            
            # Find error/failure lines (common patterns)
            error_patterns = [
                r'error:',
                r'Error:',
                r'ERROR:',
                r'failed:',
                r'Failed:',
                r'FAILED:',
                r'fatal:',
                r'Fatal:',
                r'FATAL:',
                r'assertion failed',
                r'AssertionError',
                r'Exception:',
                r'Traceback',
                r'exit code',
                r'exit status',
                r'Command failed',
            ]
            
            error_indices = []
            for i, line in enumerate(lines):
                if any(re.search(pattern, line, re.IGNORECASE) for pattern in error_patterns):
                    error_indices.append(i)
            
            # If we found errors, return context around them
            if error_indices:
                # Collect unique lines with context around errors
                result_lines = []
                result_indices = set()
                
                for err_idx in error_indices:
                    start = max(0, err_idx - context_lines)
                    end = min(len(lines), err_idx + context_lines + 1)
                    
                    for idx in range(start, end):
                        if idx not in result_indices:
                            result_indices.add(idx)
                            result_lines.append((idx, lines[idx]))
                
                # Sort by index and return lines
                result_lines.sort()
                # Limit total output
                if len(result_lines) > max_lines:
                    # Keep the lines around the last error
                    return [line for _, line in result_lines[-max_lines:]]
                return [line for _, line in result_lines]
            
            # No errors found, return the last max_lines
            return lines[-max_lines:] if len(lines) > max_lines else lines
            
    except Exception as e:
        # Silently fail if log extraction fails
        return None


