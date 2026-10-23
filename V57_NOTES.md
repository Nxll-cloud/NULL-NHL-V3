# Null’s Playbook V5.7 — logo swap only

The owner’s logo replaces the old shield/Ø SVG wherever the brand appeared: favicon (`page_icon`), `st.logo`,
sidebar lockup, tab-header marks, footers and the Home featured-matchup hero (small mark next to the kicker).
**Nothing else changed** — palette, CSS theme, fonts, layout, copy and all V5.6 functionality are as in V5.6.

The art is used as-is: resized, cropped and compressed only (no redraw). It sits on a black square, so the images get
rounded corners (mark 22 %, full lockup 14 px); no background knock-out.

| file | size | use |
|---|---|---|
| `assets/logo_full.webp` | 640×640 · 72 KB | README header, hi-res lockup |
| `assets/logo_full.jpg` | 512×512 · 83 KB | fallback |
| `assets/logo_full_360.webp` | 360×360 · 27 KB | inline sidebar lockup |
| `assets/logo_mark.webp` | 256×256 · 22 KB | crowned-N crop, hi-res |
| `assets/logo_mark.png` | 256×256 · 53 KB | `st.logo` (256-colour) |
| `assets/logo_mark_128.webp` | 128×128 · 8 KB | inline mark (tab headers, hero, footers) |
| `assets/favicon.png` / `favicon_256.png` | 64 / 256 px · 10 / 53 KB | favicon |

Removed: `logo.svg`, `logo_mark.svg`, `logo_1024.png`, `logo_mark_512.png`. `logo_data_uri()` now sniffs WebP/PNG/JPEG
(SVG still accepted) with a webp → png/jpg fallback; `test_v54_logo.py` updated for the raster assets.
