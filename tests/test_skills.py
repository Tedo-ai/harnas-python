from harnas import skills


def test_build_index_canonical_output(tmp_path):
    (tmp_path / "git_workflow.md").write_text(
        "\n".join([
            "---",
            "name: git_workflow",
            "description: Branching, commit, and PR description conventions",
            "triggers: [pr, commit]",
            "category: coding",
            "---",
            "Body",
            "",
        ]),
        encoding="utf-8",
    )

    assert skills.build_index(str(tmp_path)) == "\n".join([
        "## Skills",
        "",
        "You have access to local skills. The skill index below is enough to answer what skills are available. Do not call `load_skill` just to list skills. Call `load_skill` only when a user request matches a skill and you need its full instructions.",
        "",
        "- `git_workflow`: Branching, commit, and PR description conventions Category: coding. Triggers: pr, commit.",
    ])


def test_build_index_empty_directory(tmp_path):
    assert skills.build_index(str(tmp_path)) == ""
