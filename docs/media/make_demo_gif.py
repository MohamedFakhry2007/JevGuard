"""Regenerate docs/media/demo.gif from the running app (needs: pip install playwright pillow, and a Chromium).

    streamlit run app/streamlit_app.py --server.port 8599 &
    python docs/media/make_demo_gif.py /path/to/chromium
"""
import io
import sys

from PIL import Image
from playwright.sync_api import sync_playwright

URL = "http://localhost:8599"


def pick(pg, name):
    pg.locator("[data-testid=stSelectbox]").filter(has_text="Start from a saved example").locator("input").click()
    pg.keyboard.type(name)
    pg.wait_for_timeout(500)
    pg.keyboard.press("Enter")
    pg.wait_for_timeout(2500)


def shot(pg):
    pg.wait_for_timeout(600)
    return Image.open(io.BytesIO(pg.screenshot())).convert("RGB")


with sync_playwright() as p:
    b = p.chromium.launch(executable_path=sys.argv[1] if len(sys.argv) > 1 else None)
    pg = b.new_page(viewport={"width": 1100, "height": 1000})
    pg.goto(URL)
    pg.wait_for_selector("text=What the patient would read", timeout=30000)
    pick(pg, "s23-safe")
    pg.mouse.wheel(0, 330)
    a = shot(pg)
    pg.mouse.wheel(0, -1000)
    pick(pg, "s23-rx_disc")
    pg.mouse.wheel(0, 330)
    e = shot(pg)
    pg.get_by_text("What Jev said, check by check").scroll_into_view_if_needed()
    pg.mouse.wheel(0, 150)
    c = shot(pg)
    b.close()

frames = [im.crop((300, 0, 1100, 1000)).resize((640, 800)) for im in (a, e, c)]
pal = [f.quantize(colors=128, method=Image.Quantize.MEDIANCUT) for f in frames]
pal[0].save("docs/media/demo.gif", save_all=True, append_images=pal[1:], duration=[2200, 3200, 3200], loop=0, optimize=True)
print("wrote docs/media/demo.gif")
