import pytest

from harnas import input_file


def test_content_block_for_supported_file(tmp_path):
    path = tmp_path / "report.pdf"
    path.write_bytes(b"pdf")

    block = input_file.content_block(str(path))

    assert block["type"] == "document"
    assert block["media_type"] == "application/pdf"
    assert block["name"] == "report.pdf"
    assert block["source"] == {"kind": "base64", "data": "cGRm"}


def test_content_block_rejects_unsupported_file(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("text")

    with pytest.raises(ValueError, match="unsupported input file type"):
        input_file.content_block(str(path))
