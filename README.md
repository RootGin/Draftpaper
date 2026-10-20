# draftpaper-eww

Draftpaper architectural drafting sheet desktop suite ported to [Eww](https://github.com/elkowar/eww) (ElKowar's Wacky Widgets).

---

## Overview

`draftpaper-eww` reimagines the desktop as an engineering drafting sheet. Instead of conventional panel bars and status docks, the interface is drawn directly onto the sheet with architectural lettering, hairline rules, dot grids, and zone coordinates.

- **Drafting Sheet Canvas**: Dot grid background with zone ticks (columns 1–6, rows A–D) framed inside the display margins.
- **Engineering Title Block**: 12-cell title block in the bottom-right corner displaying time, date, sheet number, project name, network status, power state, battery health, power profile, CPU/memory usage, and hardware thermals.
- **Top Margin**: Numbered workspace indicators with status glyphs, critical hardware alerts, system notifications, and debounced OSD popups.
- **Bottom Margin**: Peripheral status, true-to-size physical scale bar, multi-display key plan, and interactive theme switcher.
- **Side Margins**: Parked window shelves with vertical lettering and crosshatching.
- **Ruled Schedule Overlays**: Tabular overlays for equipment, active processes, and git revision logs.
- **Telemetry Load Graphs**: Historical metric sparklines for CPU, memory, power, battery, temperature, and network throughput.
- **Application Register**: Fullscreen application launcher styled as an architectural register index.
- **Unified Control CLI**: Command-line tool (`bin/draftpaper-eww`) to manage windows, daemon state, graphs, schedules, and theme selection.

---

## Architecture & Layout

```
+-------------------------------------------------------------------+
|  Workspaces 1-6            Notifications / OSD            Alerts  | <- Top Margin
+----+---------------------------------------------------------+----+
|    |                                                         |    |
| P  |                                                         | P  |
| a  |                                                         | a  |
| r  |                      Dot Grid                           | r  |
| k  |                    Canvas & Tiling                      | k  |
| e  |                        Zones                            | e  |
| d  |                                                         | d  |
|    |                                                         |    |
|    |                                      +------------------+    |
|    |                                      |   Title Block    |    |
+----+--------------------------------------+------------------+----+
|  Bluetooth · Audio             Scale Bar · Key Plan · Theme       | <- Bottom Margin
+-------------------------------------------------------------------+
```

---

## Themes

The suite includes five built-in architectural color schemes:

- **Softglow**: Warm drafted paper with deep sepia ink (default).
- **Daypanel**: Clean drafting surface with crisp ink contrast.
- **Nightpanel**: Inverted dark drafting table with bright markings.
- **Blueprint**: Cyan engineering blueprint with white rules.
- **Nord**: Cool arctic drafting palette.

Switch themes via the bottom margin or CLI:
```bash
bin/draftpaper-eww theme set softglow
```

---

## Usage

### Starting the Suite

Launch the Eww daemon and open all default drafting windows:
```bash
./autostart.sh
```
or via the CLI:
```bash
bin/draftpaper-eww start
```

### CLI Commands

```bash
bin/draftpaper-eww toggle title-block
bin/draftpaper-eww toggle launcher
bin/draftpaper-eww graph cpu
bin/draftpaper-eww schedule equipment
bin/draftpaper-eww theme next
```

---

## Credits

`draftpaper-eww` is an Eww port inspired by and based on the original **[draftpaper](https://github.com/0x64616e6e/draftpaper)** Wayland desktop suite created by **[0x64616e6e](https://github.com/0x64616e6e)** (website: [draftpaper.este.systems](https://draftpaper.este.systems/)).

All credit for the original design philosophy, drafting sheet aesthetic, layout geometry, typography, and architectural concepts belongs to 0x64616e6e.

Ported and maintained for Eww by **[RootGin](https://github.com/RootGin)**.

---

## License

MIT License. See [LICENSE](LICENSE) for details.
