from __future__ import annotations
import asyncio, os
import json
from pathlib import Path
import typer
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from dotenv import load_dotenv

from .analysis import analyze as analyze_run
from .render import render_report, report_to_json
from .providers.github_provider import GitHubProvider
from .ai_analysis import analyze_with_ai, extract_error_lines


# SECURITY: This CLI tool is 100% read-only. It only performs GET requests
# to fetch and analyze CI run data. No modifications, creations, or deletions.
app = typer.Typer(help="CI Doctor: analyze a CI run URL and get a diagnosis (read-only).")
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
    
    # Check for OpenAI key if AI is requested
    openai_key = None
    if ai:
        openai_key = os.getenv("OPENAI_API_KEY")
        if not openai_key:
            console.print("[yellow]OpenAI API key not found. Set OPENAI_API_KEY env var for AI analysis.[/yellow]")
            console.print("[yellow]Continuing without AI analysis...[/yellow]")
            ai = False

    provider = GitHubProvider(token=gh_token, timeout=timeout, use_cache=not no_cache)
    
    async def run_analysis():
        try:
            return await analyze_run(provider, run_url=run_url, sample_limit=max_samples, want_logs=(save_logs or ai), save_logs_dir=Path("artifacts") if save_logs else None)
        finally:
            await provider.close()
    
    report = asyncio.run(run_analysis())

    # Perform AI analysis if requested
    ai_analysis = None
    if ai and openai_key and report.failing_jobs:
        console.print("[dim]Analyzing with AI...[/dim]")
        # Prepare job data for AI
        job_data = []
        all_log_lines = []
        for job in report.failing_jobs:
            job_data.append({
                'name': job.name,
                'conclusion': job.conclusion,
            })
            if job.log_lines:
                all_log_lines.extend(job.log_lines)
        
        error_lines = extract_error_lines(all_log_lines)
        ai_analysis = analyze_with_ai(
            workflow_name=report.workflow_name,
            failing_jobs=job_data,
            log_lines=all_log_lines,
            error_lines=error_lines,
            api_key=openai_key
        )
    
    if format_.lower() == "json":
        output = json.loads(report_to_json(report))
        if ai_analysis:
            output['ai_analysis'] = ai_analysis
        console.print(json.dumps(output, indent=2))
    else:
        render_report(report, use_ai=False)
        if ai_analysis:
            console.print()
            console.print(Rule())
            console.print("[bold]🤖 AI Analysis:[/bold]")
            console.print(Panel(ai_analysis, title="💡 AI Suggestions", border_style="cyan"))


def main():
    app()


if __name__ == "__main__":
    main()


