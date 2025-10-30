# CI Doctor

A CLI that analyzes a GitHub Actions run URL and prints a compact diagnosis.

## Install

Using pipx (recommended for CLI tools):

```bash
pipx install ci-doctor
```

Or with pip:

```bash
pip install ci-doctor
```

### Install (editable for dev)

```bash
pip install -e .
```

## Auth

Set up a GitHub Personal Access Token. See [GITHUB_TOKEN_SETUP.md](GITHUB_TOKEN_SETUP.md) for detailed instructions.

Quick start:
```bash
export GITHUB_TOKEN=ghp_...
```

### AI Analysis (Optional)

For AI-powered failure analysis, install the AI extras and set your OpenAI API key:

```bash
pip install -e ".[ai]"
export OPENAI_API_KEY=sk-...
```

**Creating an OpenAI API Key**:
1. Go to [https://platform.openai.com/api-keys](https://platform.openai.com/api-keys)
2. Sign in or create an OpenAI account
3. Click "Create new secret key"
4. Give it a name (e.g., "CI Doctor")
5. Copy the key immediately (you won't be able to see it again)
6. Add it to your environment: `export OPENAI_API_KEY=sk-...`

**Note**: AI analysis uses OpenAI's API, which may incur costs. The tool uses `gpt-4o-mini` for cost efficiency.

## Usage

```bash
# Use 'ci-doctor' or shorter alias 'cidoc'
ci-doctor analyze https://github.com/owner/repo/actions/runs/123456789
cidoc analyze <url>

# With AI-powered analysis
ci-doctor analyze <url> --ai

# JSON output
ci-doctor analyze <url> --format json > report.json

# Save logs to disk
ci-doctor analyze <url> --save-logs
```

**Note**: Logs from failing steps are automatically extracted and displayed. Use `--save-logs` to also save the full log ZIP to `./artifacts`. Use `--ai` for intelligent failure analysis (requires OpenAI API key).

## Security

**🔒 This tool is 100% READ-ONLY**

CI Doctor only performs GET requests to the GitHub API. It **cannot**:
- Modify repositories, workflows, or files
- Create, update, or delete anything
- Trigger workflow runs
- Change repository settings or permissions

The tool only reads:
- Workflow run status and metadata
- Job and step information
- Repository commit comparisons
- Logs (download only, no modification)

Use tokens with **read-only** scopes (`actions:read`, `contents:read`) only.

## Notes
- GitHub provider only in v0; provider abstraction enables Jenkins/Azure later.
- Stateless; uses live API with optional ETag cache.
