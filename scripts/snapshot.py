"""Drive a built deck in headless Chromium: press keys, take screenshots, report JS errors.

Usage: python scripts/snapshot.py deck.html out_dir "Right Right Down Right" [--presenter]
Requires: pip install playwright && playwright install chromium
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright


def main():
    html, out = Path(sys.argv[1]).resolve(), Path(sys.argv[2])
    keys = []
    for k in sys.argv[3].split():  # "ArrowRight*5" repeats a key
        name, _, n = k.partition("*")
        keys += [name] * int(n or 1)
    shots = {int(x) for x in next((a.split("=")[1] for a in sys.argv if a.startswith("--shots=")), "").split(",") if x}
    presenter = "--presenter" in sys.argv
    out.mkdir(parents=True, exist_ok=True)
    errors = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1280 if not presenter else 1600, "height": 720 if not presenter else 700})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.goto(html.as_uri() + ("?presenter" if presenter else ""))
        page.wait_for_timeout(400)
        page.screenshot(path=str(out / "00.png"))
        for i, k in enumerate(keys, 1):
            page.keyboard.press(k)
            page.wait_for_timeout(450 if (not shots or i in shots) else 40)
            state = page.evaluate("JSON.stringify(Lattice.state().cur)")
            print(f"{i:02d} {k:<10} {state}")
            if not shots or i in shots:
                page.screenshot(path=str(out / f"{i:02d}.png"))
        b.close()
    for e in errors:
        print("JS ERROR:", e)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
