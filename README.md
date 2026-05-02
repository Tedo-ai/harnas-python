# harnas-python

Python implementation of [Harnas](https://github.com/Tedo-ai/harnas) —
a specification for LLM agent harnesses. Passes 20/20 conformance
fixtures byte-identically with the
[Ruby reference](https://github.com/Tedo-ai/harnas-ruby), participates
in the 3x3 Session JSONL round-trip matrix, and ships live providers,
tools, strategies, middleware, and a manifest-driven CLI.

**Version 0.6.0** (2026-05-02). Tracks Harnas spec 0.6.0.

## Scope

This is now a peer implementation of Harnas, not just a fixture port.
It keeps the conformance-first discipline that made the port useful:
the Log, provider wire shapes, Session JSONL persistence, and fixture
outputs remain byte-identical across Ruby, Python, and Go.

The Python surface includes:

- Live Anthropic, OpenAI, and Gemini providers, buffered and streaming
- Manifest loading with provider/model overrides and env API keys
- `harnas chat` / `harnas run` plus persisted-Session operator commands
- RetryPolicy-backed provider calls and provider_error Events
- Built-in tools: read_file, write_file, edit_file, list_dir, glob,
  grep, run_shell, fetch_url
- Tool middleware: timed, logged, retried, RateLimiter, StaleReadGuard
- Compaction strategies: MarkerTail, TokenMarkerTail, SummaryTail,
  ToolOutputCap
- Permission strategies: AlwaysAllow, DenyByName, HumanApproval

## Layout

```
src/harnas/
├── event.py              — canonical Log entry shape
├── log.py                — append-only sequence
├── session.py            — id + Log + metadata
├── mutations.py          — :compact / :revert resolution
├── hooks.py              — bidirectional intervention bus
├── agent_loop.py         — Log → Projection → Provider → Ingestor loop
├── projections/          — anthropic, openai, gemini
├── ingestors/            — anthropic, openai, gemini
├── providers/            — live + streaming provider clients
├── tools/                — Tool, Registry, Runner, builtin tools, middleware
├── strategies/compaction — MarkerTail, TokenMarkerTail, SummaryTail, ToolOutputCap
├── strategies/permission — AlwaysAllow, DenyByName, HumanApproval
├── compaction/helpers.py — message_events, tool_pair_safe_range
├── actions/compact.py    — append a :compact mutation
└── conformance/          — ScriptedProvider + fixture runner

bin/conformance.py        — runs every agent fixture
bin/conformance_roundtrip.py — phase runner for Session JSONL interop
bin/harnas                — manifest + persisted-Session CLI
bin/smoke-*               — live provider smoke tests
```

## Runtime Scope

Each `Session` owns its own `hooks` registry. Strategies installed from
the conformance runner use `session.install(...)`, and `AgentLoop`
invokes `session.hooks`, so concurrent Sessions in one process do not
share strategy handlers by accident.

The Python port also exposes the small façade surface needed by the
fixtures and replay tools:

- `Agent.chat(text)` for buffered turns
- `Agent.stream(text, on_delta)` for deterministic streaming turns
- `Agent.from_session(session)` for continuing from a forked Session
- `Session.fork(at_seq=N)` for rewind-and-retry style Log branches

## Run conformance

```sh
pip install -e .[test]
python3 bin/conformance.py
```

The `bin/conformance.py` script resolves fixture paths against a sibling
checkout of [`Tedo-ai/harnas`](https://github.com/Tedo-ai/harnas). Clone
both into the same parent directory:

```
~/code/
├── harnas/         ← clone of Tedo-ai/harnas
└── harnas-python/  ← clone of Tedo-ai/harnas-python
```

Then `python3 bin/conformance.py` from `harnas-python/` will find the
fixtures at `../harnas/conformance/agents/`.

## Operator CLI

The Python port ships the persisted-Session operator commands shared
with the Ruby and Go CLIs:

```sh
python3 bin/harnas chat manifest.json
python3 bin/harnas run manifest.json --input "hello"
python3 bin/harnas inspect session.jsonl [--json]
python3 bin/harnas fork session.jsonl --at-seq N --out forked.jsonl
python3 bin/harnas diff a.jsonl b.jsonl
python3 bin/harnas project session.jsonl --manifest manifest.json [--from-seq N] [--to-seq M]
```

`project` renders the provider request body from a saved Log slice
without making a provider call. It supports the conformance-facing
Anthropic, OpenAI, and Gemini projections.

The live smoke scripts exercise both buffered and streaming providers:

```sh
ANTHROPIC_API_KEY=... bin/smoke-anthropic "say hello in one word"
OPENAI_API_KEY=... bin/smoke-openai "say hello in one word"
GEMINI_API_KEY=... bin/smoke-gemini "say hello in one word"
```

## Why Python (and Ruby first)?

The Ruby reference exists to define the spec by example; the Python
port exists to falsify the claim that the spec is Ruby-coupled and to
grow into a peer implementation. Multiple ports surface the language
idioms the spec accidentally absorbed; we found two on the way to the
initial buffered 5/5 conformance:

- The strategy `install` contract is class-level only (Ruby allows
  same-named class+instance methods; Python does not). Spec §05
  was clarified accordingly.
- The conformance stub handler now uses compact JSON rather than
  Ruby's `Hash#inspect` for the args format (was implicit, now
  normative). Spec `conformance/README.md` was updated.

Both findings are in the Harnas 0.1.0 spec.

## Changelog

See [`CHANGELOG.md`](CHANGELOG.md).

## License

[MIT](LICENSE).
