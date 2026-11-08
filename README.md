# Team lead skills

Five free Claude skills for people who run a team. They read what git, GitHub and Linear already
recorded, so you stop asking people what they did. Free, MIT, no signup, nothing to host.

One writes this morning's standup. One finds the work that quietly stopped moving before the
deadline finds it for you. One writes the weekly update. One gets you ready for a 1:1 with the
specifics instead of "how's it going". One drafts the investor update and refuses to invent a
number.

**Nothing gets sent until you send it.** These skills write. You paste.

## Install

Paste this into Claude Code:

```
https://github.com/layergen/team-lead-skills

Install these skills, then confirm /standup works.
```

Or do it yourself:

```bash
git clone https://github.com/layergen/team-lead-skills.git
cp -r team-lead-skills/skills/* ~/.claude/skills/
```

Or as a plugin:

```
/plugin marketplace add layergen/team-lead-skills
/plugin install team-lead
```

Then open any repo and type `/standup`.

## The five

| command | what you get |
| --- | --- |
| `/standup` | Today's standup, person by person, from the record. Ready to paste into Slack. |
| `/what-slipped` | PRs nobody reviewed, tickets stuck in progress, tickets marked done with no code behind them. The worst one first, with who can move it. |
| `/weekly-update` | The week as outcomes, written for your team or for someone outside it. |
| `/1on1-prep` | Specific things to thank someone for, what may be in their way, and questions worth asking. |
| `/investor-update` | The month's product work from the record, your numbers from you, and `[ASK: MRR]` where one is missing. |

## What it reads

| source | what you need |
| --- | --- |
| Git | Nothing. It reads the repo you're in. Add `--repo ../api` for more. |
| GitHub | The `gh` CLI, signed in. |
| Linear | A personal API key in `LINEAR_API_KEY`. |

All of it runs on your machine through one small script with no dependencies, and the data only
goes to the Claude session you run it in. If a source can't be read, the output says which one and
why, so a quiet week never gets confused with a broken connection.

One person showing up under three names? Put a `team.json` in the folder:

```json
{ "Ada Obi": ["ada@acme.io", "adaobi", "Ada"] }
```

## The fine print

**It can only see what got recorded.** Design, sales, support, calls and thinking don't appear in
git. Someone with no records gets "nothing in these sources", never "did nothing".

**It won't rank your team.** No commit counts, no scoreboards, no comparing people. Commit counts
measure commit habits, not work, and a tool that pretends otherwise makes your team worse.

**A stalled item is a question.** "Idle for 9 days" is a fact. Why is for you to ask.

**"Done with no code" only runs for teams that link tickets to code.** If nothing links, the check
says it skipped rather than flagging every ticket you closed.

**It's a snapshot you run by hand.** It doesn't know what people intended to do, only what the
tools show. Asking your team still matters.

## Want this every evening without running it?

[Eodly](https://eodly.io/?utm_source=github&utm_medium=skill-pack&utm_campaign=team-lead-skills)
asks your team for a one-line check-in in Slack, Discord or Telegram, checks it against GitHub and
Linear, and sends you one short report each evening. No time tracking, no screen recording. Free
for up to 5 people.

## Licence

MIT. Use it, change it, pass it on.
