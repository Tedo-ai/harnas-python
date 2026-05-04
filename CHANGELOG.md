# Changelog

All notable changes to the Python implementation of Harnas are
recorded here.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and Harnas adheres to [Semantic Versioning](https://semver.org/) on
the specification as a whole.

## [Unreleased]

### Added

- Added manifest-declared hook installation, `on_error: "fail_turn"`
  hook policy support, and terminal `runtime_error` Log events for
  harness-internal failures.
- Added `harnas.observation.CostTracker` for cumulative token usage
  tracking.
- Strategies now emit Observation-only `strategy_started` and
  `strategy_completed` events with `noop`, `mutated`, `refused`, or
  `error` effects.
- Conformance now passes 27/27 fixtures, including manifest hooks,
  fail-turn runtime errors, and strategy-event sidecars.

### Fixed

- `StaleReadGuard` now allows creation of a file that does not yet exist
  on disk while still refusing overwrites of existing files that have
  not been read in the current Session.
- Clarified `StaleReadGuard` refusal messages so LLM consumers know when
  to call `read_file` before retrying a write/edit.

## [0.8.0] — 2026-05-03

### Reference implementation (Python)

#### Changed

- Streaming transport events now emit on the Session Observation bus
  and no longer append to the durable Log. Consolidated
  `assistant_message` / `tool_use` events still append as before.
- Conformance now passes 24/24 fixtures, including the
  `with-delta-logger-sidecar` fixture.

#### Added

- Added `harnas.observation.Observation` and `DeltaLogger` for
  Observation subscriptions and opt-in sidecar JSONL persistence of
  streaming transport events.

#### Fixed

- OpenAI live streaming requests include
  `stream_options: {"include_usage": true}`, preserving non-zero usage
  in the consolidated assistant message.

## [0.7.0] — 2026-05-02

### Reference implementation (Python)

#### Added

- `assistant_message` payloads now preserve optional reasoning block
  lists.
- Anthropic, OpenAI, and Gemini ingestors capture provider reasoning
  content into `payload.reasoning` when present.
- The Anthropic projection round-trips captured reasoning as thinking
  content blocks, including signatures, for follow-up turns.
- Conformance now passes 23/23 fixtures, including reasoning capture
  for Anthropic, OpenAI, and Kimi-shaped OpenAI-compatible responses.

## [0.6.0] — 2026-05-02

### Reference implementation (Python)

#### Added

- Added full manifest loading for Python, including validation,
  provider/model overrides, env API-key resolution, strategy wiring,
  and `Agent.from_manifest`.
- Added live buffered and streaming providers for Anthropic, OpenAI,
  and Gemini, with SSE parsing that accepts LF and CRLF event
  separators.
- Added `harnas chat` and `harnas run` to the Python CLI, with
  manifest-driven execution, streaming chat output when available, and
  automatic Session JSONL saving under `~/.harnas/runs/`.
- Added `RetryPolicy` parity for provider calls, including retryable
  HTTP/network failures, configurable backoff, and correct
  `provider_failed` loop termination.
- Added tool middleware helpers: `timed`, `logged`, `retried`,
  `RateLimiter`, and Log-sourced `StaleReadGuard`.
- Added canonical built-in tools: read_file, write_file, edit_file,
  list_dir, glob, grep, run_shell, and fetch_url.
- Added `Compaction::TokenMarkerTail`,
  `Compaction::SummaryTail`, `Permission::AlwaysAllow`, and
  `Permission::HumanApproval`.
- Added live provider smoke scripts for Anthropic, OpenAI, and Gemini,
  plus a scheduled GitHub Actions workflow.
- Added unit coverage for providers, CLI chat/run, RetryPolicy,
  middleware, strategies, built-in tools, and smoke helpers.

#### Fixed

- `tool_pair_safe_range` now drops in-flight `tool_use` Events that do
  not yet have a matching `tool_result`, preventing compaction from
  orphaning active tool calls.

## [0.5.0] — 2026-05-02

### Reference implementation (Python)

#### Added

- Added a small `harnas` CLI with `inspect`, `fork`, `diff`, and
  `project` commands for persisted Session JSONL debugging.

#### Clarified

- README scope language now calls the Python port a conformance-first
  implementation with a planned parity arc, rather than a permanent
  stub.

## [0.4.0] — 2026-04-29

### Reference implementation (Python)

#### Changed

- Conformance now passes 20/20 fixtures, including provider retry/fatal
  errors, tool failure, permission denial, streaming tool failure,
  strategy composition, revert chains, Session fork/continue, system
  prompts, and large/unicode tool arguments.
- Added `Session.save` / `Session.load` and
  `bin/conformance_roundtrip.py` for Session JSONL cross-language
  round-trip conformance. The Python implementation now participates
  in the Ruby/Python/Go 3x3 persistence matrix.
- Added property-style unittest coverage for mutation idempotence,
  projection purity, dense seq assignment, fork prefixes, and
  compact/revert composition.
- Conformance inputs can now fork the active Session and verify fork
  prefix/metadata before continuing.
- Conformance inputs can now append explicit `compact` and `revert`
  Mutation Events for mutation-chain fixtures.
- Added the conformance-facing `Compaction::ToolOutputCap` strategy.
- Buffered conformance scripts can now assert the projected provider
  request before returning a response.
- Added deterministic provider-error handling for scripted providers
  and the `Permission::DenyByName` strategy used by conformance.
- Scripted streaming fixtures can now model mid-stream provider
  failures by appending `assistant_turn_failed` before raising the
  provider error.
- Added a small `Agent` façade with `chat`, `stream`, and
  `from_session` methods for parity with the Ruby reference's
  conformance-facing surface.
- `Session.fork(at_seq=N)` creates a new Session with a verbatim Log
  prefix and `forked_from` / `forked_at_seq` metadata.
- `AgentLoop` can now call a streaming-delta callback when streaming
  Events are appended.
- `Session` now owns a `hooks` registry and exposes
  `session.install(StrategyClass, **config)` for symmetry with the
  Ruby reference.
- `AgentLoop` invokes `session.hooks` instead of the process-global
  hook registry.
- Module-level `harnas.hooks` functions remain as backward-compatible
  wrappers around a process-global default registry.

## [0.2.0] — 2026-04-28

### Reference implementation (Python)

#### Changed

- Agent-level conformance now includes streaming fixtures; the Python
  runner replays `provider-script-stream.json` through the AgentLoop
  streaming path.
- `AgentLoop` accepts a deterministic streaming provider for fixture
  replay while preserving the buffered conformance path.
- The implementation now passes 7/7 conformance fixtures
  byte-identically with the Ruby reference.

## [0.1.0] — 2026-04-28

First released version of the Python implementation. It passed all five
initial buffered conformance fixtures byte-identically with the Ruby
reference, while intentionally remaining a conformance-first,
standard-library-only port rather than a full peer implementation.

[0.4.0]: https://github.com/Tedo-ai/harnas-python/releases/tag/v0.4.0
[0.2.0]: https://github.com/Tedo-ai/harnas-python/releases/tag/v0.2.0
[0.1.0]: https://github.com/Tedo-ai/harnas-python/releases/tag/v0.1.0
