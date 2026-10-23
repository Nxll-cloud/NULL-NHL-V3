# Null's Playbook, in Plain English

*A plain-language companion to the main README. Nothing here is new. It's the same information without the technical detail.*

---

## What the app is

Null's Playbook is a web app about **NHL hockey goal scorers**. For each night's games it ranks the players most likely to score, explains why, follows games live, and can compare its own estimates with sportsbook prices. Some sections, such as the numerology boards, are just for fun and are marked as entertainment only.

The current version is **5.9**.

---

## What each release added

**Version 5.9 (current)**
- **A tidier Research page.** By default it now ends at the "Top 10 Statistical Sleepers" list. Everything below that is hidden but not deleted, and it can be switched back on.
- **A smarter "who scores next" model.** It now also considers how good the opposing goalie is, how much power-play time a player gets, and how much ice time he's been getting lately. (For a full plain-English explanation, see *NEXT_GOAL_MODEL_PLAIN.md*.)
- **🚨 "Scored tonight" badges** next to any player who has already scored, across more of the app: Storylines, Live Next Goal, Edge Flags, the Home page's parlay and long-shot picks, and the Research Top 10 lists.

**Version 5.8**
- Works better on **phones**.
- The Home page gained a **suggested four-leg parlay** (four picks combined) and a **long-shot pick**.
- Scorer badges, a **Numbers match table**, **arena names** next to each game, and a new **Storylines** tab.

**Version 5.7**
- Swapped in the owner's new logo (a crowned "N") everywhere the old one appeared. Nothing else changed.

**Version 5.6**
- **Live Next Goal:** a new tab that follows games live using the NHL's official game data and shows each player's chance of scoring the next goal.
- **Goalie matchups** in the Matchup Center, using real past results between shooters and goalies.
- **Numerology boards** for each game.
- **Edge Flags:** points out where the model's view of a player differs from a sportsbook's first posted price for him to score.
- A **test against a past night of games**, with the results saved permanently so later versions can be compared fairly.

**Version 5.5**
- **EdgeLab:** a tool for comparing the model's chances with betting prices.
- **Safety checks before uploading to GitHub**, the site where the code is stored, so files don't grow too large.
- A **redesigned look** with dark, light, and high-contrast themes.
- Features from version 5.4 (Matchup Center, Track Record, goalies, Form %) were kept unchanged.

**Earlier versions**
- Nightly game analysis, data prepared ahead of time on a schedule, a phone-friendly dashboard, and optional sportsbook odds, either from an odds service or from a spreadsheet you upload.

---

## Passwords and keys (keeping secrets safe)

Some features, like live sportsbook odds, need a private access key from an outside service. The app keeps these keys in a **private settings area**. That's a local settings file on your own computer, or the hosting service's "Secrets" panel online. They are **never saved in the shared code**, and they should never be uploaded with it.

---

## How your data is saved

The app keeps a record of its predictions and how they turned out, in a small database file.

**Important if the app runs on Streamlit Community Cloud (the free online hosting service):** that service doesn't keep files permanently. When the app is redeployed, the saved record can be wiped. To avoid losing it, regularly use the **Export** button on the Track Record tab to download a backup, and import it again after a redeploy.

---

## Coming later: a live scoring ticker

There's a plan for a **live score ticker** on the Home page. It would show goals as they happen and highlight it when one of the night's top picks scores. Right now it's only an outline. It's **switched off, nothing in the app uses it, and nothing is being checked live for it**. The plan is to get scores from the NHL's own feed, with ESPN as a backup (neither needs a key) and, optionally, a third service that needs its own private key. It would check for updates only while games are being played, and politely, so it doesn't overload those services. It won't be switched on until it's fully built and tested.

---

### Points in the original README that were unclear

- **Version 5.9 and the Home accuracy card.** The detailed 5.9 notes first say the Home "daily accuracy" card is "not in V5.9 yet, merged later", then later describe it being merged. It's unclear whether it counts as part of 5.9, so it's left out above.
- **EdgeLab.** The README describes it as letting you enter your own prices and probabilities and suggesting bet sizes. The 5.8 notes say those controls were removed and EdgeLab is now a read-only comparison with live prices. The README's description seems to be out of date.
- **Track Record backup.** The README says to use the Track Record tab's Export button. The 5.8 notes say that tab is hidden by default and has to be switched back on in settings first.
- **"Line context"** in the 5.9 summary means recent ice time, not knowledge of who a player's linemates are.
- **Shot quality (5.9).** A shot-quality adjustment using MoneyPuck.com data was also merged into 5.9 and is on by default, but the README's 5.9 summary doesn't mention it.
