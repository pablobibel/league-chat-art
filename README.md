# League chat art

Convert your own local pictures into `l`/`.` text art, preview the result, then send one picture to League of Legends chat on Windows. All-chat is the default; team chat is optional.

Inspired by [aizej/image-to-ascii-for-LOL-chat](https://github.com/aizej/image-to-ascii-for-LOL-chat) and its [conversion approach](https://github.com/aizej/image-to-ascii-for-LOL-chat/blob/main/main.py). The starting width and aspect correction are conversion settings, **not verified League chat limits**.

## Setup

Install Python 3.11 or newer on Windows, then run these commands in PowerShell:

```powershell
git clone https://github.com/pablobibel/league-chat-art.git
cd league-chat-art
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Pillow handles images. PyAutoGUI supplies keyboard input. Windows APIs identify the foreground process and detect F8/Esc; the script does not read game memory or inject code into League.

Activate your own GitHub access before cloning this private repository. The virtual environment and local image/output files are not included in the repository.

## Preview and export first

Use a PNG, JPEG, WebP, or BMP file. Paths containing spaces need quotes.

```powershell
.\.venv\Scripts\python.exe .\league_art.py 'C:\Pictures\funny face.png' --preview-only
.\.venv\Scripts\python.exe .\league_art.py 'C:\Pictures\funny face.png' --preview-only --output .\art.txt
```

The terminal shows the generated art, row/message count, and estimated sending time. Preview-only mode never sends keyboard input. `--output` creates a new text file and preserves existing files; use a new filename for another export. It does not disable sending by itself, so combine it with `--preview-only` when you only want an export.

## Send one picture

```powershell
# All-chat (default)
.\.venv\Scripts\python.exe .\league_art.py 'C:\Pictures\funny face.png'

# Team chat
.\.venv\Scripts\python.exe .\league_art.py 'C:\Pictures\funny face.png' --channel team
```

1. Inspect the terminal preview.
2. Switch to an actual League game, with **chat closed**. Enable all-chat when using the default channel and use the standard chat key bindings.
3. Turn Caps Lock off and release Ctrl, Alt, Shift, and Windows keys, then press and release **F8** after the script is waiting. The game must be in the foreground; the League launcher/client does not qualify.
4. Keep League focused through the two-second countdown and sending. The script opens and sends one chat message for each row, then exits.

Press **Esc** to cancel. Detected focus loss also cancels the operation. There is no automatic resume, repeat, or retry. Script-held modifiers are released on exit.

PyAutoGUI's mouse-corner fail-safe is disabled because League can confine or hide its cursor at a screen corner after opening chat, producing false cancellations. Esc and foreground-window verification remain active throughout the run.

For all-chat, each row uses Shift+Enter to open chat, types the row, then uses Enter to submit. Team chat uses Enter to open and submit. The foreground process must be `League of Legends.exe` before sending and before each typing action. These checks are best effort: changing windows while sending should still be avoided.

The script cannot determine whether chat is actually open, whether a message arrived, or whether League rejected input. Results count **attempted rows**, not confirmed deliveries. Cancelling may leave a partial chat draft; inspect and clear it yourself. Messages already submitted cannot be recalled.

## Tune the picture

Start with a tightly cropped face or a clear silhouette against a simple background. Fine detail and text usually disappear at this size. Crop your source image before running the script if needed.

```powershell
# Increase contrast and adjust the cutoff between light and dark pixels
.\.venv\Scripts\python.exe .\league_art.py 'C:\Pictures\funny face.png' --preview-only --contrast 1.6 --threshold 145

# Swap the two characters
.\.venv\Scripts\python.exe .\league_art.py 'C:\Pictures\funny face.png' --preview-only --invert

# Adjust dimensions and give chat more time between rows
.\.venv\Scripts\python.exe .\league_art.py 'C:\Pictures\funny face.png' --width 40 --max-rows 10 --aspect 4 --line-delay 2
```

EXIF orientation is applied, transparent pixels are composited onto white, and images are converted to grayscale before contrast and threshold processing. Inversion swaps the output characters.

| Option | Default | Purpose |
| --- | --- | --- |
| `image` | Required | Local PNG, JPEG, WebP, or BMP path. |
| `--width` | `50` | Requested number of text columns. |
| `--max-rows` | `12` | Maximum rows/messages; larger results shrink proportionally in both dimensions. |
| `--aspect` | `4` | Vertical correction; larger values produce fewer rows. |
| `--contrast` | `1` | Grayscale contrast factor; `1` keeps the original contrast. |
| `--threshold` | `128` | Grayscale cutoff for choosing between `l` and `.`. |
| `--invert` | Off | Swap `l` and `.`. |
| `--channel` | `all` | `all` or `team`. |
| `--start-delay` | `2` | Countdown seconds after F8. |
| `--char-delay` | `0.01` | Delay in seconds between characters. |
| `--line-delay` | `1.5` | Delay in seconds between messages. |
| `--preview-only` | Off | Preview and exit without keyboard input. |
| `--output` | None | Save generated text to the specified file. |

Run `.\.venv\Scripts\python.exe .\league_art.py --help` for all options. The terminal font differs from League's font, so the preview is approximate. Sending time is an estimate and excludes waiting for F8 or delays introduced by the game. Each row also gets a fixed 0.2-second pause to let the chat input open. Animated PNG/WebP files use the first frame.

## Verification and compatibility

Run the automated tests without launching League:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -v
```

Tests exercise image conversion and the sending sequence using a fake keyboard backend. They do not send messages to a live game or prove that the current League client accepts the input.

**Local validation: PASS.** All 40 tests passed with Python 3.12.14, Pillow 12.3.0, and PyAutoGUI 0.9.54. The command-line help, preview/export with a spaced filename, dependency consistency check, and read-only Windows foreground/key-state adapter checks also passed. No keyboard input was sent to League during validation.

**Private-game validation status: NOT RUN.** Current glyph rendering, wrapping, automated-input compatibility, and message timing/rate behavior are unverified. A user-operated private game is required for these checks:

- [ ] Preview a small, recognizable image and confirm the characters look right in-game.
- [ ] Check every row for wrapping or truncation; reduce width if necessary.
- [ ] Confirm all-chat and team chat each reach the intended channel.
- [ ] Check that rows remain in order and the selected timing is accepted.
- [ ] Cancel during the countdown and during a row; check for a partial draft.
- [ ] Change focus during a small test and confirm sending stops without resuming.
- [ ] Confirm one F8 trigger sends one picture and the process exits afterward.
- [ ] Record the test date, League version, chat settings, dimensions, delays, and observed results before claiming compatibility.

[Riot's Terms of Service](https://www.riotgames.com/en/terms-of-service) restrict unauthorized automation and disruptive repeated messages. This project has no verified Riot approval and makes no claim that using it is account-safe. Do not use it to spam chat.
