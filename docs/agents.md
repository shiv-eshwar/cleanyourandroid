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

Install [uv](https://docs.astral.sh/uv/) so your agent can run `uvx`. The examples pin CleanYourAndroid to v0.1.1. Clients with a restricted PATH may need the full path to `uvx` and a `CLEANYOURANDROID_ADB` environment variable pointing to `adb`.

| Client | Setup |
| --- | --- |
| Claude Code | Run the [Claude MCP command](#claude-code-mcp). |
| Cursor | Merge [the stdio example](../examples/agents/mcp-servers.json) into the `mcpServers` object in `.cursor/mcp.json` for the project or `~/.cursor/mcp.json` for your user. |
| OpenCode | Merge [the OpenCode example](../examples/agents/opencode.json) into your `opencode.json` configuration. Add its entry to the existing `mcp` object. Run `opencode mcp list` to check the connection. |
| Codex | Run the [Codex MCP command](#codex-mcp). |
| Other stdio clients | Use the same command and arguments from [the stdio example](../examples/agents/mcp-servers.json) in the client's local MCP configuration. |

Keep your existing server entries when merging. Once connected, ask the client to call `list_devices`, choose the serial for your phone, and run `audit_device` or `diagnose_performance`. The server also exposes frames and standby counters. Use the CLI for any approved changes or to restore a journal.

[Cursor MCP](https://cursor.com/docs/mcp) · [OpenCode MCP](https://opencode.ai/docs/mcp-servers/) · [Claude Code MCP](https://code.claude.com/docs/en/mcp)

### Claude Code MCP

```sh
claude mcp add --transport stdio --scope user cleanyourandroid -- uvx --python 3.12 \
  --from "cleanyourandroid[mcp] @ git+https://github.com/shiv-eshwar/cleanyourandroid.git@v0.1.1" \
  cleanyourandroid-mcp
claude mcp list
```

### Codex MCP

```sh
codex mcp add cleanyourandroid -- uvx --python 3.12 \
  --from "cleanyourandroid[mcp] @ git+https://github.com/shiv-eshwar/cleanyourandroid.git@v0.1.1" \
  cleanyourandroid-mcp
codex mcp list
```

### Use an existing local install

If you already have the checkout, install the MCP extra with `python -m pip install ".[mcp]"`. Set your client's command to the absolute path of `cleanyourandroid-mcp`, with an empty argument list. OpenCode expresses that same command as a one-item array.
