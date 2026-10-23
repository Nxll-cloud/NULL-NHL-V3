# The "Next Goal" Model, in Plain English

*A plain-language companion to the technical notes. Nothing here is new. Everything comes from the existing project notes, just with the jargon taken out.*

---

## What it does

During an NHL game, the model answers one question: **who is most likely to score the next goal?**

It gives every skater in the game (not the goalies) a percentage chance of scoring next. It also leaves some of the chance for "nobody scores again", since a game can end without another goal. Add up every player's chance plus the "no more goals" chance and you get 100%.

Before a game starts, the same thinking produces a second number for each player: **the chance he scores at least once tonight**. Several other parts of the app use that number.

---

## What information it uses

Think of it as a careful fan who keeps track of a few things:

**1. How often a player shoots.**
Players who shoot a lot get more chances to score. The model starts with each player's recent shooting habits (shots per game over his last 10 games). As a game goes on, it pays more and more attention to how much he is shooting *tonight*.

**2. How often his shots go in.**
It looks at the player's scoring rate per shot this season. It deliberately pulls that rate toward the league average, so a player who got lucky on a handful of shots doesn't look like a superstar.

**3. How good his chances are tonight.**
During the game it looks at where each shot came from (how close to the net, what angle) and what kind of shot it was. A tip-in from the doorstep counts for more than a long shot from the blue line.

**4. The game situation right now.**
A team with an extra player because of a penalty (a "power play") is more likely to score next. A team that is short a player is less likely. A team that has pulled its goalie for an extra attacker changes the odds for both sides. Overtime is played three-on-three, which speeds up scoring.

**5. How much time is left.**
More time left means more chance that *someone* scores.

### Extra context added in later versions (switched on by default)

Two later releases added more pre-game context. Each one can only nudge a player's number by a limited amount:

- **The opposing goalie.** If the goalie a player faces tonight usually stops a high share of shots, that player's chances go down a little. If the goalie lets in more than usual, they go up a little. The model uses the goalie actually in net during a game, or the expected starter before it. If neither is known, it uses the team's goalies overall, and if that isn't available either, it makes no adjustment.
- **Power-play time.** Players who get a lot of ice time on the power play, and who face opponents that take a lot of penalties, get a boost. Their power-play shots are counted separately, since those go in more often.
- **Recent ice time.** If a player has been getting more ice time over the last two weeks than usual, he gets a small boost, and less ice time means a small cut. This is the meaning of the "line context" mentioned in the notes. **It does not know who his linemates are.** The notes say plainly that there's no reliable source for that.
- **Shot quality over the season.** Using public data from **MoneyPuck.com**, the model checks whether a player's shots this season tend to be dangerous ones or low-percentage ones, and adjusts a little either way. The app shows a credit to MoneyPuck wherever this data was used, as MoneyPuck's terms require. Those terms allow free use only for non-commercial purposes.

Taken together, these extras can never push a player's number above double, or below half, of what the basic model would have said. If any of this information is missing or out of date, the model simply uses the basic numbers for that part.

---

## How to read what it shows

- **The ranked list in a live game** shows each player's chance of scoring next, highest first. Arrows show who moved up or down since the last update, about every 30 seconds.
- **Before the game** the list uses only season-long information, since nothing has happened yet.
- **After the game** there is no "next goal", so the model stops predicting.
- **Shootouts are not covered.**
- Anything labelled **DEMO** is a replay of a finished game, shown for illustration, not live data.
- A 🚨 badge next to a name means that player **has already scored tonight**.

**Keep percentages in perspective.** Every skater in the game is in the running, so even the top name has a fairly small chance. In testing, the #1 name scored next 7.5% of the time (see below). That's well above random, but most of the time someone else scores.

---

## Where you'll see it

- The **Live Next Goal** tab
- The **Matchup Center** live panel, and its list of the shooters most dangerous to each goalie
- The **live strip** on the Home page
- Indirectly, behind other features: **Edge Flags** (compares the model's pre-game chance with a sportsbook's opening price), **EdgeLab** (compares it with current prices), and the Home page's **four-leg parlay** and **long shot** picks

---

## How well has it been tested?

The original version of the model was replayed against one full night of real games: **April 4, 2026: 15 games, 106 goals** (not counting shootouts). It was only shown information it would actually have had at each moment.

Here's how often the player it ranked #1 actually scored the next goal, compared with two simple alternatives:

| | The model | Just pick the guy who shoots the most per game | Pick at random |
|---|---|---|---|
| Model's #1 pick scored next | 7.5% | 5.7% | 2.8% |
| Scorer was in the top 3 | 19.8% | 22.6% | 8.3% |
| Scorer was in the top 5 | 31.1% | 30.2% | 13.9% |
| #1 pick *on the team that scored* scored | 10.4% | 15.1% | 5.6% |

**What the project's own review concluded:**
- It clearly beats guessing at random (about 2.7 times better for the #1 pick).
- Across the whole game it's roughly level with the simple "who shoots the most" approach.
- It's **worse** than that simple approach at picking *which teammate* scores. The review says this is because it lets a few shots early in a game reshuffle teammates too much.
- In the pre-game ranking, the top-ranked shooter scored at least once in 40.0% of games, the same as the simple approach.
- The pre-game "chance to score at least once tonight" numbers matched reality well. They ran slightly low, on a night that averaged 7.1 goals per game.
- The moment-to-moment numbers were **too confident at the top**: players given 10% to 25% scored next only 7% to 10% of the time. They were **slightly too cautious at the bottom**: players given 0% to 2% scored next 1.7% of the time.

**Where it misses most:**
- **Defencemen.** They scored 16 goals that night and were never in the model's top 3.
- **Early in games**, before many shots have been taken: 0 of 12 correct at #1.
- **Blowouts**, where depth players score. The original model had no information about ice time or line deployment.
- **Rebounds**, which tend to go to players who don't shoot much overall.
- Its best situations were **empty-net and power-play goals**.

**What hasn't been tested:**
- Whether it beats the betting market. That comparison is built but couldn't be run, because no real historical opening betting lines were available. Nothing was made up to fill the gap.
- The newer extras (goalie, power-play time, recent ice time, shot quality). The notes say the test has **not yet been rerun** with them, so the results above describe the original version only.
- It's one night of games. The notes caution against tuning the model to that same night, and say any change should be checked against a different night.

---

## Limits and caveats

- Many of the model's settings were **chosen by hand from general hockey knowledge**, not learned from data. The technical notes call its percentages "model estimates, uncalibrated".
- It doesn't know linemates, only ice time.
- During a live game, power plays and penalty kills are handled at the team level, not player by player.
- Early in the season there's little shot-quality data, so that adjustment does very little.
- A gap between the model's number and a sportsbook's price is **not a guarantee of value** (from the odds notes).
- The numerology boards elsewhere in the app are **entertainment only** and are not part of this model.

---

## Why it matters

The model turns the live flow of a game (who's shooting, from where, with what manpower, against which goalie) into one easy-to-read ranking of who's likely to score next. It also feeds the app's pre-game picks and price comparisons. It has been checked honestly against a real night of hockey, and its weak spots are written down rather than hidden.

---

### Points in the original notes that were unclear

- **"Line context"** sounds like the model knows linemates. It doesn't. It uses recent ice time as a stand-in.
- One note compares players with their "season" shooting rate, but another note and the code say the live app actually uses **the last 10 games**. The test found little difference between the two (top-pick rate 7.5% either way).
- The test results describe the **original version only**. The release notes don't say how the newer extras perform.
