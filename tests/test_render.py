import pytest

from grist_sync import render

_block_examples = [
    (
        "# <TAG>\nfoo = 42\n\n# </TAG>\n",
        "# <TAG>\n# foo = 42\n#\n# </TAG>\n",
    ),
    (
        "# <TAG>\nfoo = 42\n# </TAG>\n# <TAG>\nbar = 42\n# </TAG>\n",
        "# <TAG>\n# foo = 42\n# </TAG>\n# <TAG>\n# bar = 42\n# </TAG>\n",
    ),
]


@pytest.mark.parametrize("text, expected", _block_examples)
def test_comment_chunks(text, expected):
    rendered = render._comment_chunks(text, "TAG")
    assert rendered == expected


@pytest.mark.parametrize("text, expected", [(x[1], x[0]) for x in _block_examples])
def test_uncomment_chunks(text, expected):
    rendered = render._uncomment_chunks(text, "TAG")
    assert rendered == expected


def test_local_to_grist_uncomments_grist_chunks():
    rendered = render.local_to_grist("# <GRIST>\n# foo = 42\n\n# </GRIST>\n")
    assert rendered.endswith("# <GRIST>\nfoo = 42\n\n# </GRIST>\n")


def test_local_to_grist_comments_local_chunks():
    rendered = render.local_to_grist("# <LOCAL>\nfoo = 42\n\n# </LOCAL>\n")
    assert rendered.endswith("# <LOCAL>\n# foo = 42\n#\n# </LOCAL>\n")


def test_grist_to_local_comments_grist_chunks():
    text = "# <GRIST>\nfoo = 42\n# </GRIST>\n"
    round_trip = render.grist_to_local(text)
    assert "# foo = 42" in round_trip


def test_grist_to_local_uncomments_local_chunks():
    text = "# <LOCAL>\nfoo = 42\n# </LOCAL>\n"
    round_trip = render.grist_to_local(text)
    assert "foo = 42" in round_trip


def test_render_adds_git_tag():
    text = "foo = 42\n"
    rendered = render.local_to_grist(text)
    assert rendered.startswith("# git@")


_full_examples = [
    """\
# <LOCAL>
foo = 42

bar = "bam"
# </LOCAL>
# <GRIST>
# foo = 24
#
# bar = "qux"
# </GRIST>
""",
    """\
def f():
#<LOCAL>
  enabled = True
#</LOCAL>
#<GRIST>
#  enabled = False
#</GRIST>
  return enabled
""",
]


@pytest.mark.parametrize("text", _full_examples)
def test_render_round_trip_preserves_source_text(text):
    rendered = render.local_to_grist(text)
    round_trip = render.grist_to_local(rendered)
    assert round_trip == text
