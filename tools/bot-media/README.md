# Bot media

The pictures the bot sends: the welcome (`welcome.html`) and the five steps of
the «How to use» guide (`guide.html`), in every language the bot speaks. Texts
live in `copy.js`; the guide's own words are in `backend/app/utils/bot_intro.py`.

```sh
pip install playwright        # plus backend/requirements.txt and frontend/node_modules
python capture.py             # screenshots of the Mini App → shots/<lang>/
python render.py              # HTML → frontend/public/bot/*.png
```

`capture.py` runs its own backend on a throwaway SQLite database and its own
`next dev`, so stop yours first. `CHROMIUM_PATH` points both scripts at a
Chromium of your own when Playwright's is not installed.

After a redraw, bump `BOT_MEDIA_VERSION` on the server: Telegram keeps a
picture by its address and would go on sending the old one.
