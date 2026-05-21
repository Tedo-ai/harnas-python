from harnas.capability_manifest import (
    MemoryCapabilityManifestStore,
    capability_manifest_ref,
)


def test_capability_manifest_ref_is_stable():
    a = {"tools": ["read_file"], "provider": {"kind": "mock"}}
    b = {"provider": {"kind": "mock"}, "tools": ["read_file"]}

    assert capability_manifest_ref(a) == capability_manifest_ref(b)
    assert capability_manifest_ref(a).startswith("cap_sha256_")


def test_memory_capability_manifest_store():
    store = MemoryCapabilityManifestStore()
    manifest = {"tools": ["read_file"]}
    manifest_ref = store.put(manifest)

    assert store.get(manifest_ref) == manifest
