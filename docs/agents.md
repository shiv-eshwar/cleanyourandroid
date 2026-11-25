# Use CleanYourAndroid with a coding agent

Run the agent on the computer with the authorized ADB connection. An agent in the cloud typically cannot see a local USB device or reach your Wi-Fi debugging port. Use a local agent, or a trusted self-hosted worker that can reach the phone.

Install [ADB and the CLI](../README.md#quick-start) first if you want the agent to run the full workflow. The skill gives the agent instructions for using the CLI. The optional [MCP server](#read-only-mcp) exposes device discovery and diagnostics to clients that support local stdio tools.

## Install the skill

Use the same [Agent Skill](../skills/cleanyourandroid/SKILL.md) with Claude Code, Cursor, OpenCode, Codex, and other compatible clients. With Node.js installed, run this from the project where you use your agent:

```sh
npx --yes skills add shiv-eshwar/cleanyourandroid --skill cleanyourandroid --agent claude-code cursor opencode
```

Keep only the agents you want in the `--agent` list, or add `codex` to install it there too. Add `--global` to install it for your user instead of the current project.

For a manual install, copy the entire `skills/cleanyourandroid` directory from the checkout into a skill directory below. Restart the agent if it doesn't discover the skill in your current session.

| Agent | Directory in your project | Native plugin |
| --- | --- | --- |
| Claude Code | `.claude/skills/` | [Claude Code plugin](#claude-code-plugin) |
| Cursor | `.cursor/skills/` or `.agents/skills/` | Use the portable skill |
| OpenCode | `.opencode/skills/`, `.agents/skills/`, or `.claude/skills/` | Use the portable skill |
| Codex | `.agents/skills/` | [Codex plugin](#codex-plugin) |
| Any local coding agent | Its Agent Skills directory, if supported | Open the checkout and paste [PROMPT.md](../PROMPT.md) if the agent supports shell tools |

Ask the agent to “Use CleanYourAndroid to audit my phone over ADB. Show me your findings before applying any changes.”

[Claude Code skills](https://code.claude.com/docs/en/skills) · [Cursor skills](https://cursor.com/docs/skills) · [OpenCode skills](https://opencode.ai/docs/skills/) · [Agent Skills standard](https://agentskills.io/)

### Claude Code plugin

```sh
claude plugin marketplace add shiv-eshwar/cleanyourandroid
claude plugin install cleanyourandroid@cleanyourandroid
```

Start a new Claude Code session and invoke `/cleanyourandroid:cleanyourandroid`. You can also register an existing checkout by passing its absolute path to `claude plugin marketplace add`. [Claude Code plugin installation](https://code.claude.com/docs/en/plugins/install).

### Codex plugin

```sh
codex plugin marketplace add shiv-eshwar/cleanyourandroid
codex plugin add cleanyourandroid@cleanyourandroid
```

Start a new Codex session and invoke `$cleanyourandroid`. To use an existing checkout, pass its absolute path to `codex plugin marketplace add`.

## Read-only MCP

Install [uv](https://docs.astral.sh/uv/) so your agent can run `uvx`. The examples pin CleanYourAndroid to [the 0.3.0 implementation](https://github.com/shiv-eshwar/cleanyourandroid/commit/c2c5a8c57364e4f410586941dacdc5c67154655f). Clients with a restricted PATH may need the full path to `uvx` and a `CLEANYOURANDROID_ADB` environment variable pointing to `adb`.

| Client | Setup |
| --- | --- |
| Claude Code | Run the [Claude MCP command](#claude-code-mcp). |
| Cursor | Merge [the stdio example](../examples/agents/mcp-servers.json) into `mcpServers` in `.cursor/mcp.json` or `~/.cursor/mcp.json`, then [approve the local server](#cursor-mcp). |
| OpenCode | Follow the [OpenCode instructions](#opencode-mcp) for your installed major version. |
| Codex | Run the [Codex MCP command](#codex-mcp). |
| Other stdio clients | Use the same command and arguments from [the stdio example](../examples/agents/mcp-servers.json) in the client's local MCP configuration. |

Keep your existing server entries when merging. Once connected, ask the client to call `list_devices`, choose the serial for your phone, and run `audit_device` or `diagnose_performance`. The server also exposes frames and standby counters. Use the CLI for any approved changes or to restore a journal.

[Cursor MCP](https://cursor.com/docs/mcp) · [OpenCode MCP](https://opencode.ai/docs/mcp-servers/) · [Claude Code MCP](https://code.claude.com/docs/en/mcp)

### Claude Code MCP

```sh
claude mcp add --transport stdio --scope user cleanyourandroid -- uvx --python 3.12 \
  --from "cleanyourandroid[mcp] @ git+https://github.com/shiv-eshwar/cleanyourandroid.git@c2c5a8c57364e4f410586941dacdc5c67154655f" \
  cleanyourandroid-mcp
claude mcp list
```

### Cursor MCP

After adding the example, enable CleanYourAndroid in Cursor's MCP settings. In Cursor CLI, approve the new local server explicitly and check for its tools.

```sh
cursor-agent mcp enable cleanyourandroid
cursor-agent mcp list-tools cleanyourandroid
```

### OpenCode MCP

On **OpenCode 1.x**, merge [the OpenCode example](../examples/agents/opencode.json) into the existing `mcp` object in `opencode.json`. Verify it with `opencode mcp list`. This was tested with OpenCode 1.19.6.

**OpenCode 2.x** uses `mcp.servers`. Its CLI can write the appropriate entry for the current project.

```sh
opencode mcp add cleanyourandroid -- uvx --python 3.12 \
  --from "cleanyourandroid[mcp] @ git+https://github.com/shiv-eshwar/cleanyourandroid.git@c2c5a8c57364e4f410586941dacdc5c67154655f" \
  cleanyourandroid-mcp
opencode mcp list
```

OpenCode 2.2.5 and 2.3.0 accepted the entry in testing, but their standalone MCP listing did not start the server. Use the portable skill with the local CLI on those builds, or use OpenCode 1.x for the verified MCP path.

### Codex MCP

```sh
codex mcp add cleanyourandroid -- uvx --python 3.12 \
  --from "cleanyourandroid[mcp] @ git+https://github.com/shiv-eshwar/cleanyourandroid.git@c2c5a8c57364e4f410586941dacdc5c67154655f" \
  cleanyourandroid-mcp
codex mcp list
```

### Use an existing local install

If you already have the checkout, install the MCP extra with `python -m pip install ".[mcp]"`. Set your client's command to the absolute path of `cleanyourandroid-mcp`, with an empty argument list. OpenCode expresses that same command as a one-item array.
