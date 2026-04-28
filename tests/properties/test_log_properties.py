import random
import unittest

from harnas import mutations
from harnas.log import Log
from harnas.projections.anthropic import Anthropic
from harnas.session import Session


def serialize(events):
    return [(event.seq, event.type, event.payload) for event in events]


def append_random_message(log: Log, index: int) -> None:
    if index % 2 == 0:
        log.append(type="user_message", payload={"text": f"message-{index}-{random.randint(0, 10000)}"})
    else:
        log.append(
            type="assistant_message",
            payload={
                "text": f"message-{index}-{random.randint(0, 10000)}",
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 0, "output_tokens": 0},
            },
        )


def random_log(message_count: int | None = None, compact: bool = True) -> Log:
    log = Log()
    count = message_count or random.randint(1, 12)
    for index in range(count):
        append_random_message(log, index)
    if compact and count >= 4 and random.random() < 0.6:
        upper = random.randint(1, count - 2)
        log.append(
            type="compact",
            payload={"replaces": list(range(upper + 1)), "summary": f"summary up to {upper}"},
        )
    return log


class LogPropertiesTest(unittest.TestCase):
    def test_mutations_apply_is_idempotent(self):
        for _ in range(100):
            log = random_log()
            once = mutations.apply(log)
            twice = mutations.apply(once)
            self.assertEqual(serialize(twice), serialize(once))

    def test_projections_are_pure(self):
        for _ in range(100):
            log = random_log()
            projection = Anthropic(model="claude-test", max_tokens=128)
            self.assertEqual(projection(log), projection(log))

    def test_append_preserves_dense_seq_order(self):
        for _ in range(100):
            log = random_log(compact=False)
            self.assertEqual([event.seq for event in log], list(range(log.size)))

    def test_fork_preserves_the_selected_prefix(self):
        for _ in range(100):
            session = Session.create()
            for index in range(random.randint(1, 12)):
                append_random_message(session.log, index)
            at_seq = random.randint(0, session.log.size - 1)
            forked = session.fork(at_seq=at_seq)

            self.assertEqual(serialize(forked.log), serialize(list(session.log)[: at_seq + 1]))
            self.assertEqual(forked.metadata["forked_from"], session.id)
            self.assertEqual(forked.metadata["forked_at_seq"], at_seq)

    def test_compact_revert_composes_back_to_original_effective_stream(self):
        for _ in range(100):
            log = random_log(message_count=random.randint(2, 8), compact=False)
            original = mutations.apply(log)
            compact = log.append(
                type="compact",
                payload={"replaces": list(range(log.size)), "summary": "temporary summary"},
            )
            log.append(type="revert", payload={"revokes": compact.seq})

            self.assertEqual(serialize(mutations.apply(log)), serialize(original))


if __name__ == "__main__":
    unittest.main()
