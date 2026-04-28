# harnas-python

Python implementation of [Harnas](https://github.com/Tedo-ai/harnas) —
a specification for LLM agent harnesses. Passes 7/7 conformance
fixtures byte-identically with the
[Ruby reference](https://github.com/Tedo-ai/harnas-ruby).

**Version 0.1.0** (2026-04-28). Tracks Harnas spec 0.1.0.

## Scope

This is a **conformance-first stub**: standard library only, aimed at
the conformance fixtures. It demonstrates that
the Harnas specification is genuinely portable — same Log, same wire
shapes, byte-identical fixture output.

It is **not** at feature parity with the Ruby reference yet. Missing:

- Live HTTP providers (Anthropic / OpenAI / Gemini, buffered + streaming)
- Compaction strategies beyond MarkerTail (TokenMarkerTail, SummaryTail,
  ToolOutputCap)
- Permission strategies (AlwaysAllow, DenyByName, HumanApproval)
- Tool middleware (Timed, Logged, Retried, RateLimiter, StaleReadGuard)
- Built-in tools (read_file / write_file / grep / glob / shell / fetch)
- Agent façade
- Log/Session JSONL persistence
- Provider-error events + RetryPolicy in AgentLoop

Closing those is incremental work that follows the Ruby reference's
patterns; nothing is spec-blocked.

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
├── tools/                — Tool, Registry, Runner
├── strategies/compaction — MarkerTail
├── compaction/helpers.py — message_events, tool_pair_safe_range
├── actions/compact.py    — append a :compact mutation
└── conformance/          — ScriptedProvider + fixture runner

bin/conformance.py        — runs every fixture under the spec's
                            conformance/agents/ directory
```

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

## Why Python (and Ruby first)?

The Ruby reference exists to define the spec by example; the Python
port exists to falsify the claim that the spec is Ruby-coupled. Two
implementations is the minimum for the word "portable" to mean
something. Two ports surface the language idioms the spec accidentally
absorbed; we found two on the way to the initial buffered 5/5
conformance:

- The strategy `install` contract is class-level only (Ruby allows
  same-named class+instance methods; Python does not). Spec §05
  was clarified accordingly.
- The conformance stub handler now uses compact JSON rather than
  Ruby's `Hash#inspect` for the args format (was implicit, now
  normative). Spec `conformance/README.md` was updated.

Both findings are in the Harnas 0.1.0 spec.

## License

[MIT](LICENSE).
