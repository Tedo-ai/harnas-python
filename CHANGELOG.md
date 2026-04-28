# Changelog

All notable changes to the Python implementation of Harnas are
recorded here.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and Harnas adheres to [Semantic Versioning](https://semver.org/) on
the specification as a whole.

## [Unreleased]

### Reference implementation (Python)

#### Changed

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

[0.2.0]: https://github.com/Tedo-ai/harnas-python/releases/tag/v0.2.0
[0.1.0]: https://github.com/Tedo-ai/harnas-python/releases/tag/v0.1.0
