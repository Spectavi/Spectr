from pathlib import Path

import spectr
from textual.css.stylesheet import Stylesheet


def test_default_stylesheet_parses() -> None:
    css_path = Path(spectr.__file__).with_name("default.tcss")
    assert css_path.exists(), f"Missing stylesheet: {css_path}"

    stylesheet = Stylesheet()
    stylesheet.read(css_path)
