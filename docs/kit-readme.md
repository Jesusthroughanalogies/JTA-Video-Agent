# JTA Long-Form Video Agent: build notes

Everything the agent needs except the code. Load `AGENT_SYSTEM_PROMPT.md` as the system prompt and give the agent read/write access to `knowledge/`.

## Recommended stack

- **Claude Agent SDK** (Python or TypeScript), running on a machine with ffmpeg and enough disk for 4K clips (50 GB free is comfortable).
- Long-running, resumable: save the episode state to `episodes/<id>/state.json` after each phase so a crash or a checkpoint wait doesn't lose work.

## Tools the agent needs

| Tool | Used for | Notes |
|---|---|---|
| File system + shell | Knowledge base, rendering, ffmpeg | Built into the Agent SDK |
| Google Drive | Inputs, review cuts, finals | Drive API or an MCP server |
| Higgsfield | AI video generation | Higgsfield MCP server, or its API |
| ElevenLabs | Speech-to-text with word timestamps, music, sound effects | ElevenLabs API or MCP; needs music and SFX access (the full connector, not the restricted one) |
| Animation renderer | [ANIM] and [TEXT] shots | Remotion (React) or a Python/SVG renderer like the one used for the colouring book; keep reusable analogy components in `assets/animations/` |
| ffmpeg | Assembly, audio mix, loudness, final render | Or Remotion for the whole timeline |
| Image check | QC of every generated clip | Claude's own vision: extract 3 frames per clip and inspect them |
| YouTube Data API | Later: automated upload | Not used yet. The humans upload by hand from the `final/` upload pack until 3 to 5 episodes have gone cleanly. |
| YouTube Analytics API | 48h and 7-day performance | Same OAuth |
| Web search + fetch | Topic research and fact-checking | |
| Messaging | Checkpoint messages | The Claude chat. The agent pauses until a reply contains "approved" or changes. |

## Drive layout

```
/JTA/
  Episodes/
    ep001-does-god-exist/
      inputs/        <- Matt and Jack drop voiceover, clips, photos here
      generated/     <- agent: AI clips, animations, music
      review/        <- agent: rough cuts for checkpoint D
      final/         <- agent: final MP4, thumbnails, srt, upload text
  Assets/            <- reusable animations, music beds, brand files (fonts, logo)
  Knowledge/         <- master copy of knowledge/ (the agent syncs it every run)
```

## Checkpoints

| | When | Human decision |
|---|---|---|
| A | After topic proposal | Approve topic, angle and analogy |
| B | After script | Approve script, then record |
| C | After shot list + cost estimate | Approve spend |
| D | After rough cut | Notes or approve |

## First run plan

1. Episode 001's script is already written (Claude Doc). Start the agent at Phase 3 once the voiceover and clips are in the Drive.
2. On episode 001, have the agent test two Higgsfield models on the first 5 hero shots and record the winners in `learnings.md`.
3. Review its episode file afterwards and correct anything in the style bible that didn't hold up.
