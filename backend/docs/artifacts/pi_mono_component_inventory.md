# Pi Mono Component Inventory

Phase: 6V-P0

## Files Reviewed

- `pi-mono/README.md`
- `pi-mono/package.json`
- `pi-mono/LICENSE`
- `pi-mono/packages/agent/README.md`
- `pi-mono/packages/agent/src/agent.ts`
- `pi-mono/packages/agent/src/agent-loop.ts`
- `pi-mono/packages/agent/src/types.ts`
- `pi-mono/packages/ai/README.md`
- `pi-mono/packages/ai/package.json`
- `pi-mono/packages/ai/src/types.ts`
- `pi-mono/packages/ai/src/stream.ts`
- `pi-mono/packages/ai/src/api-registry.ts`
- `pi-mono/packages/ai/src/providers/register-builtins.ts`
- `pi-mono/packages/ai/src/providers/transform-messages.ts`
- `pi-mono/packages/ai/src/providers/openai-responses.ts`
- `pi-mono/packages/ai/src/providers/openai-responses-shared.ts`
- `pi-mono/packages/ai/src/providers/simple-options.ts`
- `pi-mono/packages/ai/src/models.ts`
- `pi-mono/packages/coding-agent/README.md`
- `pi-mono/packages/coding-agent/src/core/agent-session.ts`
- `pi-mono/packages/coding-agent/src/core/messages.ts`
- `pi-mono/packages/coding-agent/src/core/system-prompt.ts`
- `pi-mono/packages/coding-agent/src/core/resource-loader.ts`
- `pi-mono/packages/coding-agent/src/core/tools/index.ts`
- `pi-mono/packages/coding-agent/src/core/tools/read.ts`
- `pi-mono/packages/coding-agent/src/core/tools/edit.ts`
- `pi-mono/packages/coding-agent/src/core/tools/bash.ts`
- `pi-mono/packages/coding-agent/src/core/tools/edit-diff.ts`
- `pi-mono/packages/coding-agent/src/core/compaction/compaction.ts`
- `pi-mono/packages/coding-agent/src/core/compaction/utils.ts`
- `pi-mono/packages/tui/README.md`
- `pi-mono/packages/tui/src/tui.ts`
- `pi-mono/packages/web-ui/README.md`
- `pi-mono/packages/web-ui/src/components/AgentInterface.ts`
- `pi-mono/packages/web-ui/src/tools/javascript-repl.ts`
- `pi-mono/packages/mom/README.md`
- `pi-mono/packages/pods/README.md`

## Component Summary

| Area | Role | Adopt This Phase |
|---|---|---|
| `packages/agent` | Stateful agent loop, event stream, tool execution, hooks | Concept only |
| `packages/ai` | Provider adapters, message transform, model registry, token/cost | Interface ideas only |
| `packages/coding-agent` | CLI coding harness, filesystem and shell tools, sessions, compaction | Only context-transform/compaction ideas |
| `packages/web-ui` | Chat UI web components, artifacts, sandbox JS REPL | Not adopted |
| `packages/tui` | Terminal UI differential renderer | Not adopted |
| `packages/mom` | Slack bot with shell/filesystem access | Not adopted |
| `packages/pods` | vLLM GPU pod management | Not adopted |

## Adopted Concepts

- Agent loop with bounded model turns and tool-result feedback.
- Tool definition as name, description, schema, and execution function.
- JSON-schema style argument validation before tool execution.
- Sequential and bounded parallel tool execution, returning results in tool-call order.
- Event contract modeled after `agent_start`, `turn_start`, `message_update`, `tool_execution_*`, `agent_end`.
- Context transform before model invocation.
- Abort/deadline propagation and terminal status.

## Explicitly Excluded

- `bash`, `read`, `write`, `edit`, `grep`, `find`, `ls`.
- Any filesystem, shell, JS/Python REPL, Slack, GPU pod, or Web UI runtime.
- Direct reuse of pi-mono TypeScript packages in request path.
- Direct provider/model access from generic runtime.
