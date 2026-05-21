import base64

from harnas.attachments import FilesystemStore, InlineStore, MemoryStore
from harnas.log import Log


def test_filesystem_store_put_get_and_list_referenced(tmp_path):
    store = FilesystemStore(tmp_path)
    ref = store.put(b"image-bytes", "image/png")

    assert ref.uri.startswith("attachment://")
    assert ref.source == {"kind": "ref", "uri": ref.uri}
    assert store.get(ref.uri) == (b"image-bytes", "image/png")

    log = Log()
    log.append(
        type="user_message",
        payload={
            "content": [
                {"type": "image", "media_type": "image/png", "source": ref.source}
            ]
        },
    )
    assert store.list_referenced(log) == [ref.uri]

    store.delete(ref.uri)
    assert not store.exists(ref.uri)


def test_memory_and_inline_stores():
    memory = MemoryStore()
    ref = memory.put(b"pdf", "application/pdf")

    assert memory.exists(ref.uri)
    assert memory.get(ref.uri) == (b"pdf", "application/pdf")

    inline_ref = InlineStore().put(b"abc", "image/jpeg")
    assert inline_ref.uri is None
    assert inline_ref.source == {
        "kind": "base64",
        "data": base64.b64encode(b"abc").decode("ascii"),
    }
