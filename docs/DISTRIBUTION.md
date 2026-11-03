# Distributing 917v-code-review in the 917Ventures organization

This repository is both the **plugin** (`.claude-plugin/plugin.json`) and a one-plugin **marketplace** (`.claude-plugin/marketplace.json`, marketplace name `917ventures`, plugin source `"./"`). Host it as a **private GitHub repository**.

> Assumption: the repository lives at `github.com/917ventures/917v-code-review`. If the org or repo name differs, replace `917ventures/917v-code-review` everywhere below. If 917Ventures already runs a central marketplace repository, use [Option B](#option-b-add-it-to-an-existing-org-marketplace) instead.

## 1. Publish the repository (maintainers)

```bash
cd 917v-code-review
git init -b main && git add -A && git commit -m "917v-code-review v1.0.0"
gh repo create 917ventures/917v-code-review --private --source . --push
claude plugin tag .            # creates the 917v-code-review--v1.0.0 release tag after validating manifests
git push --tags
```

Before every release, run:

```bash
python3 -m unittest discover -s tests -v
claude plugin validate . --strict
```

## 2. Access to a private repository

Claude Code clones marketplaces with **the user's own git credentials**. It has no token setting of its own.

- **SSH** works out of the box when `ssh -T git@github.com` succeeds. Claude Code tries SSH first.
- **HTTPS** needs a non-interactive credential helper:
  ```bash
  gh auth login
  gh auth setup-git
  ```
  To skip the SSH probe, set `CLAUDE_CODE_PLUGIN_PREFER_HTTPS=1`.
- **CI or headless**: export `GH_TOKEN` (read access to the repo), then run `gh auth setup-git`. A token in the environment only works through a credential helper.
- Background auto-updates use the same credentials and never prompt. A failed refresh keeps the installed copy. Set `CLAUDE_CODE_PLUGIN_KEEP_MARKETPLACE_ON_FAILURE=1` to keep the existing marketplace checkout when a refresh cannot authenticate.
- Developers must be members of a GitHub team with **read** access to the repository.

## 3. Roll out to the organization (administrators)

### Option A: managed settings (recommended)

Deploy these keys through **server-managed settings** (claude.ai admin console), MDM, or a `managed-settings.json` file:

```json
{
  "extraKnownMarketplaces": {
    "917ventures": {
      "source": { "source": "github", "repo": "917ventures/917v-code-review" },
      "autoUpdate": true
    }
  },
  "enabledPlugins": {
    "917v-code-review@917ventures": true
  }
}
```

- `extraKnownMarketplaces` registers the marketplace for every user.
- `enabledPlugins` with `true` installs and enables the plugin. With `false`, it blocks the plugin.
- `autoUpdate: true` lets clients pick up new versions in the background, about ten minutes after a session starts.
- To allow-list marketplaces org-wide, add `strictKnownMarketplaces`. The list must include every marketplace you still want to allow, because an empty list blocks all of them:
  ```json
  "strictKnownMarketplaces": [
    { "source": "github", "repo": "917ventures/917v-code-review" },
    { "source": "skills-dir" }
  ]
  ```

### Option A2: per-repository opt-in

To roll out project by project instead, commit the same `extraKnownMarketplaces` and `enabledPlugins` keys to a project's `.claude/settings.json`. Claude Code offers to install the marketplace when a developer trusts the folder.

### Option A3: Claude Team / Enterprise plugin sync

In **claude.ai → Organization settings → Plugins & skills**, connect the GitHub repository. Members then receive the plugin without needing their own git credentials for it.

### Option B: add it to an existing org marketplace

Add an entry to the central marketplace's `.claude-plugin/marketplace.json`:

```json
{
  "name": "917v-code-review",
  "source": { "source": "github", "repo": "917ventures/917v-code-review", "ref": "917v-code-review--v1.0.0" },
  "description": "Standardized read-only code review with validated findings and reports in docs/code-review/.",
  "category": "development"
}
```

To pin an exact commit, add `"sha": "<full 40-character commit sha>"`. When both are present, the `sha` wins.

## 4. Install and use (developers)

```bash
claude plugin marketplace add 917ventures/917v-code-review
claude plugin install 917v-code-review@917ventures
```

Or inside Claude Code: `/plugin marketplace add 917ventures/917v-code-review`, then `/plugin install 917v-code-review@917ventures`. Restart the session, or run `/reload-plugins`.

Check the installation:

```bash
claude plugin list                                   # shows 917v-code-review@917ventures
claude plugin details 917v-code-review@917ventures   # 4 commands, 1 skill, 8 agents
```

Then, in any repository:

```text
/917v-code-review:review
/917v-code-review:review-diff --branch main
/917v-code-review:security
/917v-code-review:architecture
```

Prerequisites on each machine: `git` and `python3` 3.8 or newer.

## 5. Versioning and upgrades

- The version comes from `.claude-plugin/plugin.json` `version` (semver). **Bump it on every release.** Clients only update when the version changes. Record each release in `CHANGELOG.md`, then tag it with `claude plugin tag .`.
  - MAJOR: changes to report file names, `findings.json` shape, or command names.
  - MINOR: new agents, checks, or stack support.
  - PATCH: fixes and prompt tuning.
- **Users** update with:
  ```bash
  claude plugin marketplace update 917ventures
  claude plugin update 917v-code-review@917ventures
  ```
  Then restart or run `/reload-plugins`. With `autoUpdate: true` this happens automatically.
- **Pinning**: set `"ref": "<tag>"` (and optionally `"sha"`) on the marketplace source, or use `owner/repo#ref` when adding the marketplace. A pinned allow-list entry in `strictKnownMarketplaces` must carry the same `ref`.
- **Rollback**: point `ref` at the previous tag, or reinstall from it.

## 6. Data handling note for security reviewers

The plugin runs inside each developer's Claude Code session under the organization's existing Claude data policies. It adds:
- No network calls. The scripts are offline and stdlib-only, and the dashboard makes no external requests.
- No MCP servers and no hooks.
- Writes only to `docs/code-review/` in the reviewed repository.
- Online dependency audits only when the developer explicitly authorizes them in the conversation.
