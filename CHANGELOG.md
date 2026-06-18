# Changelog

All notable changes to the Python implementation of Harnas are
recorded here.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and Harnas adheres to [Semantic Versioning](https://semver.org/) on
the specification as a whole.

## [Unreleased]

### Added

- Added v0.20 durability primitives: harnas-jcs-v1 canonicalization,
  Event `content_hash`, storage adapters, and the OCC `expected_next_seq`
  append fence.
- Added fixture-gated tests for the §24 oracle corpus and §21 storage law
  fixtures.

### Changed

- Bumped Python package metadata, MCP client version, and `harnas.__version__`
  to 0.20.0. Validated against fixtures version `0.20.0`: 75/75.
- Added conformance replay support for malformed streaming provider
  frames. Validated against the expanded fixture set.
- Added a README drift check that compares public version and fixture-count
  claims with package metadata and the checked-out spec.
- Added conformance aliases for the MarkerTail, hook, and fork canary
  fixtures. Validated against the expanded 75-fixture spec set.

## [0.19.4] — 2026-06-03

### Changed

- Lockstep spec patch release. Validated against fixtures version
  `0.19.4`: 70/70.
- Enforced §19's dense Event `seq` invariant when loading Session
  JSONL, failing loudly on duplicate, gapped, or reordered rows.
- Confirmed file-backed loading already fails loudly on torn final
  JSONL rows, satisfying the scoped S8 no-silent-corruption law.
- Bumped Python package metadata, MCP client version, and
  `harnas.__version__` to 0.19.4.

## [0.19.3] — 2026-06-01

### Changed

- Lockstep spec patch release. Validated against fixtures version
  `0.19.3`: 70/70.
- Conformance runner now honors `isolation.json` repeat checks so a
  fixture can assert that multiple Sessions run in one process without
  leaking mutable state.
- Scoped the built-in `bash_session` registry to each built-in handler
  bundle instead of one process-global registry.
- Bumped Python package metadata, MCP client version, and
  `harnas.__version__` to 0.19.3.

## [0.19.2] — 2026-06-01

### Changed

- Lockstep spec patch release. Validated against fixtures version
  `0.19.2`: 69/69.
- Confirmed projections preserve assistant text alongside co-occurring
  tool calls for Anthropic, OpenAI, and Gemini.
- Bumped Python package metadata, MCP client version, and
  `harnas.__version__` to 0.19.2.

## [0.19.1] — 2026-05-31

### Changed

- Lockstep spec patch release. Validated against fixtures version
  `0.19.1`: 66/66.
- Confirmed Anthropic projections preserve assistant text alongside
  co-occurring reasoning blocks on later turns.
- Bumped Python package metadata, MCP client version, and
  `harnas.__version__` to 0.19.1.

## [0.19.0] — 2026-05-24

### Added

- Added UTC ISO 8601 timestamps to Log events and preserved timestamps
  across Session save/load.
- Added canonical assistant usage metadata with total/cache/reasoning
  token fields, raw provider usage, and provenance.
- Added provider/model identity on assistant provider-response events.
- Added optional `tool_result.payload.approval` metadata with the v0.19
  approval decision shape.

### Changed

- Lockstep spec release. Validated against fixtures version `0.19.0`:
  65/65.
- Bumped Python package metadata, MCP client version, and
  `harnas.__version__` to 0.19.0.

## [0.18.2] — 2026-05-22

### Added

- Added `shell_type` resolution for `harnas.builtin.bash_session` tool
  config and validated against fixtures version `0.18.2`: 62/62.

### Changed

- Audited `bash_session` process handling for Windows portability and
  guarded Unix-only process-group setup/signaling behind platform checks.
- Bumped Python package metadata and `harnas.__version__` to 0.18.2.
- Lockstep patch release driven by AgentStaple's Windows preview
  packaging work.

## [0.18.1] — 2026-05-22

### Added

- Added event-id preservation checking to Session save/load conformance.
- Added spawn-agent reciprocity conformance: `spawn_agent` now creates a
  child Session with reciprocal delegation metadata and an initial task
  `user_message`.

### Changed

- Lockstep patch release driven by foss/harnas spec audit findings.
- Validated against fixtures version `0.18.1`: 61/61.
- Bumped Python package metadata and `harnas.__version__` to 0.18.1.
- Audited capability manifest hashing against Go and Ruby; the v0.18.1
  sample manifest hashes identically across all three implementations.

## [0.18.0] — 2026-05-21

### Added

- Lockstep spec release. Validated against fixtures version `0.18.0`.
- Added subagent delegation event support, Session header delegation
  metadata, capability manifest helpers, and cross-session projection
  helpers.
- Added support for projection conformance fixtures via
  `expected-projections.jsonl`.
- Added optional `harnas.builtin.spawn_agent`, which records an
  `agent_spawn` receipt and returns generated child identifiers.
- Conformance now passes 59/59 fixtures, including the five subagent
  delegation fixtures.
- Bumped Python package metadata and `harnas.__version__` to 0.18.0.

## [0.17.0] — 2026-05-21

### Added

- Added multimodal content block support for text, image, and PDF
  document message content.
- Added AttachmentStore helpers: filesystem, memory, and inline stores.
- Updated Anthropic, OpenAI, Gemini, and Ollama projections for
  multimodal content and provider capability mismatch fallback.
- Added CLI `--input-file` support for image and PDF attachments.
- Updated `harnas.transcript.project` to render non-text content
  placeholders.

### Changed

- Lockstep spec release. Validated against fixtures version `0.17.0`.
- Conformance now passes 54/54 fixtures, including the eight
  multimodal content fixtures.
- Bumped Python package metadata and `harnas.__version__` to 0.17.0.

## [0.16.0] — 2026-05-21

### Added

- Added `credential/proxy`, a `:pre_tool_use` strategy that injects
  credential-backed headers into supported tool arguments while keeping
  credential values out of the Log and Observation stream.
- `fetch_url` now accepts optional request headers so credential/proxy can
  authorize HTTP calls without exposing secrets to the model.

### Changed

- Lockstep spec release. Validated against fixtures version `0.16.0`.
- Conformance now passes 46/46 fixtures, including
  `with-credential-proxy-injection`.
- Bumped Python package metadata and `harnas.__version__` to 0.16.0.

## [0.15.0] — 2026-05-21

### Added

- Added `harnas.mcp`, a Model Context Protocol adapter package with
  HTTP POST and stdio transports, MCP content flattening, Harnas tool
  descriptor translation, dynamic passthrough tool handlers, custom
  HTTP headers, lazy initialization, and degraded startup handling.
- Tool handlers may now optionally accept a second `config` argument
  carrying the tool's manifest config map. Existing single-argument
  handlers continue to work unchanged.

### Changed

- First non-lockstep release. `harnas-ruby` remains at v0.14.1 with no
  functional change, and the spec remains at v0.14.1 with no spec
  change. The lockstep discipline applies to spec changes; library
  feature additions may now ship independently per implementation.

## [0.14.1] — 2026-05-21

### Added

- Conformance runner now supports `--fixtures-from`, can be invoked as
  `python -m harnas.conformance`, and reports the fixtures version from
  the spec repo `VERSION` file.
- Added packed-wheel conformance CI: build the wheel, install it in a
  fresh virtualenv, and run conformance against the installed artifact.

### Changed

- Validated against fixtures version `0.14.1`.

## [0.14.0] — 2026-05-21

### Added

- Added `sandbox/network`, a tool-boundary network strategy with exact host
  allow/deny enforcement for `fetch_url`.
- Extended `harnas.builtin.bash_session` so `run` accepts an optional
  per-command `env` object whose variables do not persist in the shell
  session.

### Changed

- Updated `harnas.builtin.read_file` to accept `offset` and `limit`, return
  `cat -n` style line-numbered output, and reject binary files.
- Conformance now passes 45/45 fixtures.

## [0.13.0] — 2026-05-18

### Added

- Added `guard/health`, a pre-provider health-check strategy.
- Extended `guard/repetition` to detect repeated approval rejections.
- Added Ollama buffered and streaming providers using Ollama's
  OpenAI-compatible `/v1/chat/completions` endpoint, plus
  `bin/smoke-ollama`.

## [0.12.0] — 2026-05-18

### Added

- Added `sandbox/write`, `guard/repetition`, `guard/timeout`, and
  `guard/cost_budget` strategies.
- Added `--output-format ndjson` for `harnas run`.
- Applied the shared CLI exit-code taxonomy and partial stdout flush on
  exit-1 agent failures.
- Conformance now passes 39/39 fixtures.

## [0.11.0] — 2026-05-17

### Added

- Promoted `harnas.builtin.bash_session` to the conformable surface. It
  preserves shell working directory and environment changes across named
  sessions and returns both cumulative transcript fields and
  command-local stdout/stderr.
- Added adopter helper surfaces: `harnas.runtime.Runtime`,
  `harnas.transcript.project`, and `harnas.tools.snapshot`.
- Conformance now passes 34/34 fixtures, including the four
  `bash_session` fixtures.
- Bumped Python package metadata and `harnas.__version__` to 0.11.0.

## [0.10.0] — 2026-05-10

### Added

- Added `harnas.skills.build_index`, which scans a skills directory
  and emits the canonical `## Skills` system-prompt section.
- Added the `harnas.builtin.load_skill` built-in tool with
  config-driven `skills_dir`, frontmatter stripping, skill-name
  validation, and empty-body support.
- Conformance now passes 30/30 fixtures, including `with-skills` and
  `with-skills-invalid-name`.
- Bumped Python package metadata and `harnas.__version__` to 0.10.0.

### Fixed

- OpenAI projection now serializes tool-call argument JSON compactly and
  with sorted keys, matching Ruby/Go and the stricter `expect_request`
  fixtures.

## [0.9.3] — 2026-05-10

### Informative

- Tracks the v0.9.3 spec, which adds non-normative ecosystem
  conventions for skills and MCP mappings. No Python runtime behavior
  changes; the `load_skill` built-in and skills-index helper are
  planned for v0.10.
- Bumped Python package metadata and `harnas.__version__` to 0.9.3.

## [0.9.2] — 2026-05-08

### Conformance

- Tracks the v0.9.2 spec, which hardens `with-tool-call-openai` to
  assert on the second projected request via `expect_request`. The
  Python OpenAI projection already conformed to the clarified contract
  (folds `:tool_use` into the preceding assistant message's
  `tool_calls[]`, emits `:tool_result` as `role: "tool"`, normalizes
  `content` to `None` when `tool_calls[]` is present); this release
  bumps the version in lockstep so "running spec X means impl X"
  stays simple. No code changes.

## [0.9.1] — 2026-05-05

### Trust polish

- Updated README version and fixture-count language to match the
  verified v0.9.1 surface.
- Bumped Python package metadata and `harnas.__version__` to 0.9.1.
- Added normal push/PR CI for pytest, py_compile, and conformance.

### v0.9.1

#### Added

- Manifest tool entries may now declare opaque `config`; the Python
  loader stores it in the Session manifest snapshot and makes it
  available to handlers as `config=`.
- Conformance now passes 28/28 fixtures, including
  `with-tool-config-roundtrip`.

## [0.9.0] — 2026-05-05

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

[0.19.4]: https://github.com/Tedo-ai/harnas-python/releases/tag/v0.19.4
[0.19.3]: https://github.com/Tedo-ai/harnas-python/releases/tag/v0.19.3
[0.19.2]: https://github.com/Tedo-ai/harnas-python/releases/tag/v0.19.2
[0.19.1]: https://github.com/Tedo-ai/harnas-python/releases/tag/v0.19.1
[0.19.0]: https://github.com/Tedo-ai/harnas-python/releases/tag/v0.19.0
[0.18.2]: https://github.com/Tedo-ai/harnas-python/releases/tag/v0.18.2
[0.18.1]: https://github.com/Tedo-ai/harnas-python/releases/tag/v0.18.1
[0.18.0]: https://github.com/Tedo-ai/harnas-python/releases/tag/v0.18.0
[0.17.0]: https://github.com/Tedo-ai/harnas-python/releases/tag/v0.17.0
[0.16.0]: https://github.com/Tedo-ai/harnas-python/releases/tag/v0.16.0
[0.15.0]: https://github.com/Tedo-ai/harnas-python/releases/tag/v0.15.0
[0.14.1]: https://github.com/Tedo-ai/harnas-python/releases/tag/v0.14.1
[0.14.0]: https://github.com/Tedo-ai/harnas-python/releases/tag/v0.14.0
[0.13.0]: https://github.com/Tedo-ai/harnas-python/releases/tag/v0.13.0
[0.12.0]: https://github.com/Tedo-ai/harnas-python/releases/tag/v0.12.0
[0.11.0]: https://github.com/Tedo-ai/harnas-python/releases/tag/v0.11.0
[0.10.0]: https://github.com/Tedo-ai/harnas-python/releases/tag/v0.10.0
[0.9.3]: https://github.com/Tedo-ai/harnas-python/releases/tag/v0.9.3
[0.9.2]: https://github.com/Tedo-ai/harnas-python/releases/tag/v0.9.2
[0.9.1]: https://github.com/Tedo-ai/harnas-python/releases/tag/v0.9.1
[0.9.0]: https://github.com/Tedo-ai/harnas-python/releases/tag/v0.9.0
[0.8.0]: https://github.com/Tedo-ai/harnas-python/releases/tag/v0.8.0
[0.7.0]: https://github.com/Tedo-ai/harnas-python/releases/tag/v0.7.0
[0.6.0]: https://github.com/Tedo-ai/harnas-python/releases/tag/v0.6.0
[0.5.0]: https://github.com/Tedo-ai/harnas-python/releases/tag/v0.5.0
[0.4.0]: https://github.com/Tedo-ai/harnas-python/releases/tag/v0.4.0
[0.2.0]: https://github.com/Tedo-ai/harnas-python/releases/tag/v0.2.0
[0.1.0]: https://github.com/Tedo-ai/harnas-python/releases/tag/v0.1.0
