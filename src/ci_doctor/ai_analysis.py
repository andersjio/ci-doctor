"""AI-powered analysis of CI failures using OpenAI."""
from __future__ import annotations
from typing import List, Optional
import json


def analyze_with_ai(
    workflow_name: str,
    failing_jobs: List[dict],
    log_lines: List[str],
    error_lines: List[str],
    api_key: str
) -> Optional[str]:
    """
    Use OpenAI to analyze a CI failure and provide suggestions.
    
    Returns a concise analysis and suggested fix, or None if analysis fails.
    """
    try:
        from openai import OpenAI
        
        client = OpenAI(api_key=api_key)
        
        # Prepare context
        job_summary = []
        for job in failing_jobs:
            job_summary.append(f"- {job['name']}: {job.get('conclusion', 'unknown')}")
        
        # Focus on the most recent error lines
        recent_logs = "\n".join(log_lines[-100:])  # Last 100 lines
        recent_errors = "\n".join(error_lines[-20:])  # Last 20 error lines
        
        prompt = f"""Analyze this CI/CD failure and provide a concise diagnosis.

Workflow: {workflow_name}

Failed Jobs:
{chr(10).join(job_summary)}

Recent Logs (last 100 lines):
```
{recent_logs}
```

Key Error Messages (last 20 lines):
```
{recent_errors}
```

Please provide:
1. A 1-2 sentence diagnosis of what went wrong
2. A brief suggested fix (1-2 sentences)
3. If applicable, the likely cause (code change, dependency, configuration, etc.)

Keep the response under 150 words total. Be specific and actionable."""

        response = client.chat.completions.create(
            model="gpt-4o-mini",  # Using cheaper, faster model
            messages=[
                {"role": "system", "content": "You are a CI/CD expert helping diagnose build failures. Be concise and actionable."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=200,
            temperature=0.3  # Lower temperature for more deterministic outputs
        )
        
        return response.choices[0].message.content.strip()
        
    except ImportError:
        return "AI analysis requires OpenAI package. Install with: pip install 'ci-doctor[ai]' or pip install -e '.[ai]'"
    except Exception as e:
        return f"AI analysis failed: {str(e)}"


def extract_error_lines(log_lines: List[str]) -> List[str]:
    """Extract lines that likely contain error information."""
    error_patterns = ['error', 'Error', 'ERROR', 'failed', 'Failed', 'FAILED', 
                     'fatal', 'Fatal', 'FATAL', 'Exception', 'Traceback', 
                     'assertion', 'AssertionError', 'exit code', 'exit status']
    
    error_lines = []
    for line in log_lines:
        if any(pattern in line for pattern in error_patterns):
            error_lines.append(line)
    
    return error_lines

