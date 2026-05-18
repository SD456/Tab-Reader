# Tab Reader

A small desktop app for practicing along with sheet music or guitar tabs.
Open a PDF, load the matching MP3 or WAV, hit Play — the PDF auto-scrolls in
sync with the song. Per-song settings (start delay, scroll speed, zoom) are
remembered, so each tune keeps its own configuration.

## Features

- Open any PDF as a continuous, scrollable strip.
- Play MP3 or WAV files through your default Windows audio output.
- Auto-scroll begins after a configurable **start delay** (so you can sync the
  scroll to the actual moment the music starts in your tab).
- Adjustable **scroll speed**, **zoom**, and **volume** — all live.
- **Playlist sidebar** of PDF+audio pairs; click an entry to load both at once.
  The playlist persists between sessions.
- **Save** per-song settings; they reload automatically the next time you open
  that audio file.
- Manual scrolling (mouse wheel / scrollbar) works any time, and auto-scroll
  picks up from wherever you leave it.
- Spacebar = Play / Pause.

## Requirements

- Python 3.10 or newer (Windows, macOS, or Linux).
- The Python packages listed in `requirements.txt`:
  - `pymupdf` — PDF rendering
  - `pillow` — image handling
  - `pygame` — audio playback
  - `customtkinter` — the UI

## Installation

### Easy way (Windows)

Double-click **`run_tab_reader.bat`**. The first launch will install any
missing dependencies into your user Python and then start the app. Subsequent
launches go straight to the app.

### Manual install

From the folder containing `tab_reader.py`:

```bash
pip install -r requirements.txt
python tab_reader.py
```

If you keep multiple Python versions around, use the one you want explicitly,
e.g. `py -3.12 -m pip install -r requirements.txt`.

## How to use

1. **Open PDF** — pick the tab/sheet music PDF. It renders as one long scroll.
2. **Open Audio** — pick the matching `.mp3` or `.wav`. If you've used this
   audio file before, the app restores the saved start delay, scroll speed,
   and zoom automatically.
3. **Set Start delay** — how many seconds *after* you press Play the
   auto-scroll should begin. Useful if there's an intro or count-in before the
   notation begins on page 1.
4. **Set Scroll speed** — pixels per second. Drag the slider while the song
   plays to dial it in until the cursor stays on the right bar.
5. **Set Zoom** — 40 % to 300 %. Re-renders the PDF and keeps you at roughly
   the same musical position.
6. **Volume** — adjusts the song's playback volume (does not affect anything
   else on your system).
7. **Play / Pause** — toggles playback and the auto-scroll together. Spacebar
   does the same thing.
8. **Stop** — rewinds the audio to the start.
9. **Reset** — sends the PDF view back to the top without touching audio.
10. **Save settings for song** — writes the current delay / speed / zoom to a
    settings file, keyed by audio filename. Next time you load this song,
    they're restored.

You can also scroll manually at any time with the mouse wheel or the
scrollbar; auto-scroll just continues from wherever you've moved to.

## Playlist

The left sidebar holds a persistent playlist of PDF+audio pairs.

- **+ Add** — opens two file pickers: first the PDF, then the audio. The new
  entry appears at the bottom of the list, named after the audio file.
- **Click an entry** — loads both that PDF and that audio together. If you'd
  previously saved per-song settings (delay / speed / zoom) for that audio,
  they're restored automatically.
- **− Remove** — click an entry to select it (it turns indigo), then hit
  Remove to delete it from the list.

The playlist is saved automatically every time it changes, so it's there next
time you open the app.

## Audio output device

The app uses whatever output Windows is currently set as default. If you have
multiple audio devices (speakers, headphones, audio interface) and want to
pin Tab Reader to a specific one, open **Settings → System → Sound → Volume
mixer** and assign `python.exe` (or the launcher you started it with) to the
device you want. Changes made while the app is running aren't picked up — just
restart the app to switch.

## Where settings are stored

Per-song settings are written to:

```
%USERPROFILE%\.tab_reader_settings.json     (Windows)
~/.tab_reader_settings.json                 (macOS / Linux)
```

The playlist is written to:

```
%USERPROFILE%\.tab_reader_playlist.json     (Windows)
~/.tab_reader_playlist.json                 (macOS / Linux)
```

Both are plain JSON — safe to inspect, edit, or delete to start fresh.

## Troubleshooting

- **"customtkinter is required" dialog** — run the manual install command
  above, or use the `.bat` launcher which installs everything for you.
- **Audio won't play** — confirm the file actually plays in another player
  first. WAV files in unusual codecs (e.g. ADPCM) sometimes need converting
  to standard PCM. Re-saving as MP3 from any audio app fixes this.
- **PDF renders blurry when zoomed in a lot** — that's expected; the source
  is being scaled up. Higher-resolution source PDFs zoom better.
- **Auto-scroll feels off-tempo** — the speed slider goes up to 300 px/s; for
  very fast tabs, increase Zoom *and* speed together so a constant musical
  pace looks right at your chosen page size.
