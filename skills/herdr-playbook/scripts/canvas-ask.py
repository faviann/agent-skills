#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["textual==8.2.8"]
# ///
"""Ask the user one question on the canvas.

Usage: canvas-ask.py <question> <options.json> <answer.json>
options.json holds [{"label": ..., "preview": ...}]; previews are plain text.
On a pick it writes {"choice": <label>} to answer.json and exits; q quits without writing.
"""
import json
import sys
from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.widgets import Footer, Header, OptionList, Static

QUESTION = sys.argv[1]
OPTIONS = json.loads(Path(sys.argv[2]).read_text())
ANSWER = sys.argv[3]


class Ask(App):
    TITLE = QUESTION
    CSS = "#choices { width: 40%; height: 1fr; } #preview { width: 1fr; height: 1fr; padding: 1 2; border: round $accent; }"
    BINDINGS = [("q", "quit", "Quit without answering")]

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            yield OptionList(*[o["label"] for o in OPTIONS], id="choices")
            yield Static(OPTIONS[0]["preview"], id="preview", markup=False)
        yield Footer()

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        self.query_one("#preview", Static).update(OPTIONS[event.option_index]["preview"])

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        Path(ANSWER).write_text(json.dumps({"choice": OPTIONS[event.option_index]["label"]}))
        self.exit()


if __name__ == "__main__":
    Ask().run()
