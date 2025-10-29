# GitHub Token Setup Guide

CI Doctor requires a GitHub Personal Access Token (PAT) with read permissions to analyze GitHub Actions runs.

## Required Permissions (Read-Only)

**🔒 IMPORTANT: CI Doctor is READ-ONLY. Use only these read permissions:**

Your token needs the following **read-only** scopes:
- **`actions:read`** - To read workflow runs, jobs, and logs (NO write access)
- **`contents:read`** - To read repository contents for comparing commits (NO write access)

**DO NOT grant write permissions** such as:
- ❌ `actions:write` - Not needed and could allow modifications
- ❌ `contents:write` - Not needed and could allow file changes
- ❌ `workflow` - Not needed (this is for updating workflows)
- ❌ Any other write/delete/modify permissions

The tool will fail safely if these permissions are missing.

## Accessing Organization Repositories

**Important**: If you need to access GitHub Actions in an organization you don't own:

1. **You must be a member** of that organization with at least read access to the repositories
2. **The organization must allow** Personal Access Tokens (some organizations restrict PATs)
3. **Your token automatically has access** to any organization where you're a member - no special setup needed

### Checking Organization Access

Before creating a token, verify:
- You can view the repository in your browser (you have access)
- You can see the Actions tab on the repository

### If Your Organization Restricts PATs

Some organizations require:
- **Fine-grained Personal Access Tokens** (newer token type)
- **OAuth Apps** instead of personal tokens
- **Organization-owned tokens** (created by org admins)

**Contact your organization administrator** if:
- You get an error that PATs are not allowed
- You need organization-administered tokens
- You need to set up an OAuth App instead

See [Organization Token Policy](https://docs.github.com/en/organizations/managing-programmatic-access-to-your-organization/setting-a-personal-access-token-policy-for-your-organization) for more details.

## Step-by-Step Instructions

### Option A: Classic Personal Access Token (Simpler)

1. **Go to GitHub Token Creation Page**
   - Direct link: [https://github.com/settings/tokens/new](https://github.com/settings/tokens/new)
   - Or navigate: GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic) → Generate new token

2. **Configure Your Token**
   - **Note**: Give your token a descriptive name (e.g., "CI Doctor CLI - Read Only")
   - **Expiration**: Choose your preferred expiration (or no expiration for convenience)
   - **Scopes**: **ONLY** check this box:
     - ✅ `repo` - For private repos, this gives read access to Actions and contents
     - ✅ `public_repo` - For public repos only (if you only need public repo access)
   
   **Note**: Classic tokens don't have granular read-only scopes. The `repo` scope includes read access. However, CI Doctor will ONLY use GET requests, so it cannot write even with this scope.
   
   **⚠️ If your organization requires fine-grained tokens**, use Option B below.

### Option B: Fine-Grained Personal Access Token (More Secure)

1. **Go to Fine-Grained Token Creation**
   - Direct link: [https://github.com/settings/tokens?type=beta](https://github.com/settings/tokens?type=beta)
   - Or navigate: GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token

2. **Configure Your Token**
   - **Repository access**: Select the repositories you need (or "All repositories")
   - **Permissions**: Under "Repository permissions":
     - ✅ `Actions: Read-only` (this is the read-only version)
     - ✅ `Contents: Read-only` (this is the read-only version)
   - **Account permissions**: Leave as "No access" (not needed)

**⚠️ Security Warning**: Do NOT grant:
- ❌ `Actions: Write` - Allows modifying workflows
- ❌ `Contents: Write` - Allows modifying files
- ❌ `Workflow: Write` - Allows changing workflow files
- ❌ Any write, delete, or admin permissions

3. **Generate Token**
   - Click **"Generate token"** at the bottom of the page
   - **Important**: Copy the token immediately - you won't be able to see it again!

4. **Set Up Your Token**

   **Option A: Environment Variable (Recommended)**
   ```bash
   export GITHUB_TOKEN=ghp_your_token_here
   ```
   
   To make it persistent, add it to your `~/.bashrc`, `~/.zshrc`, or `~/.profile`:
   ```bash
   echo 'export GITHUB_TOKEN=ghp_your_token_here' >> ~/.zshrc
   source ~/.zshrc
   ```

   **Option B: Use .env File**
   ```bash
   # Copy the example file
   cp .env.example .env
   
   # Edit .env and add your token
   echo "GITHUB_TOKEN=ghp_your_token_here" > .env
   ```

   **Option C: Command Line Flag**
   ```bash
   ci-doctor analyze <url> --token ghp_your_token_here
   ```

## Verify Your Setup

Test that your token is working:
```bash
ci-doctor analyze https://github.com/owner/repo/actions/runs/123456789
```

If you see an authentication error, double-check:
- The token has the correct scopes (`actions:read`, `contents:read`)
- The token hasn't expired
- The token is correctly set in your environment or passed via `--token`

## Security Notes

- 🔒 Keep your token secret - never commit it to version control
- 🔒 Add `.env` to `.gitignore` (already included)
- 🔒 Use environment variables or `.env` files rather than passing tokens via command line in scripts
- 🔒 Consider using fine-grained tokens (Beta) for more granular permissions if available

## Troubleshooting

**Error: "Unauthorized. Check token scopes"**
- Ensure your token has both `actions:read` and `contents:read` permissions
- Regenerate your token if permissions were modified

**Error: "Missing GitHub token"**
- Verify the `GITHUB_TOKEN` environment variable is set: `echo $GITHUB_TOKEN`
- Or use the `--token` flag: `ci-doctor analyze <url> --token <your-token>`

## Direct Links

- [Create New Token (Classic)](https://github.com/settings/tokens/new)
- [Manage Existing Tokens](https://github.com/settings/tokens)
- [Token Documentation](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/creating-a-personal-access-token)

