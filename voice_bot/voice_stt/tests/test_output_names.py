from stt.output import render_markdown
from stt.schema import Utterance


def test_markdown_uses_display_names_in_time_order():
    utterances = [
        Utterance(session_id="s", text_raw="", speaker="111", start=1.0, end=2.0, text="嗨你好", confidence=0.9, flags=[]),
        Utterance(session_id="s", text_raw="", speaker="222", start=2.5, end=3.0, text="今天好累", confidence=0.9, flags=[]),
        Utterance(session_id="s", text_raw="", speaker="333", start=4.0, end=5.0, text="好", confidence=0.9, flags=[]),
    ]
    text = render_markdown(utterances, title="t", meta={}, names={"111": "tino", "222": "ping"})
    lines = [line for line in text.splitlines() if line.startswith("[")]
    assert lines[0].startswith("[00:01] **tino**：嗨你好")
    assert lines[1].startswith("[00:02] **ping**：今天好累")
    assert "**333**" in lines[2]  # no name known: falls back to the id
