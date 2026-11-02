# JTA Long-Form Style Bible (v1, Nov 2026)

The long-form look is separate from the short-form reels. Update this file when a learning proves a rule wrong.

## The look in one line

Cinematic AI footage for the world and the story; clean 2D motion graphics for the analogies; scripture as elegant text cards; the founders' real voices and real photos holding it together.

## Visual layers

| Layer | When to use it | Look |
|---|---|---|
| [AI] cinematic video | Bible scenes, nature, cosmos, human moments, metaphors in the real world | Photoreal, filmic, shallow depth of field, natural or golden light, subtle film grain, 16:9 |
| [ANIM] 2D motion graphics | The analogy pictures (dominoes, dials, painting, archer etc), logic steps, diagrams, comparisons | Flat, clean shapes. Deep navy background (#0E1A2B) with warm gold (#E8B04B) as the accent, off-white (#F4EFE6) for lines and text. Smooth eased motion, no bounce. |
| [TEXT] scripture and quotes | Every Bible verse and every quoted person | Title font IM Fell DW Pica, off-white on a darkened, slow-moving background. Reference underneath in small caps. On screen long enough to read twice. |
| [CLIP] / [PHOTO] founders | Intro, outro, personal story | Warm film grade, slow push or pan on stills |
| [STOCK] | Fallback only, when AI or animation can't do it | Graded to match the AI footage |

Each analogy keeps one consistent design across all its appearances in a video (the same domino, the same dial panel, the same painting). Reuse analogy assets across episodes when the same picture returns.

## Pacing

- New visual every 4 to 6 seconds. Never hold a shot longer than 8 seconds unless it is a text card or a deliberate pause.
- Hook: the first 5 seconds must show the question visually and pose it in words.
- Each part ends with a visual transition (the analogy frame completing and sliding away).

## Depiction rules

- God the Father: only as light. Never a figure.
- Jesus: from behind, in silhouette, or by His hands. Same look every time: plain off-white robe, brown outer cloak, shoulder-length dark hair, sandals. AI video can't keep a face consistent, so never show His face.
- Biblical settings: first-century Judea and Galilee for the New Testament (stone houses, dusty roads, olive trees, oil lamps). No modern objects, no European cathedral imagery in ancient scenes.
- Suffering and the crucifixion: wide, distant, silhouetted, never graphic.

## AI prompt formula (Higgsfield)

Build every [AI] prompt in this order:

`[shot type and camera move], [subject and action], [setting and period], [lighting and time of day], [lens and look], [mood]`

Then add the negatives: `no text, no watermark, no modern objects, no visible face on Jesus, no distorted hands`.

Example:
`Slow dolly forward, a robed man seen from behind walks a dusty road toward a small stone village, first-century Galilee with olive trees, soft dawn light with long shadows, 35mm cinematic shallow depth of field with subtle film grain, peaceful and hopeful. No text, no watermark, no modern objects, no visible face, no distorted hands.`

- Duration 5 to 8 seconds per clip. Generate slightly longer than needed so you can trim.
- Hero shots (opening, part openers, emotional peaks, the final shot): 2 variants, pick the best.
- Model choice: record which model worked for which shot type in `learnings.md` and follow it. Until there is data, test 2 models on the first 5 hero shots of episode 1 and keep the winner per category (cosmos, landscape, crowds, close-up hands, interiors).

## Audio

- Voiceover is king: normalise to about -16 LUFS for the voice, final mix around -14 LUFS integrated (YouTube's playback level).
- Music sits clearly under the voice (roughly 18 to 22 dB below during speech), rises in pauses and at part endings.
- Music: ElevenLabs. One main theme per video, cinematic and warm (piano, strings, soft pads). Builds at revelations, resolves at the end of each part.
- Sound effects: sparing. Domino clicks, dial clicks, soft whooshes on transitions, a low impact on the title. Never cartoonish.

## Captions

- Upload a full `.srt` file for accessibility and search.
- On screen, animate only 1 to 3 key words per part (the Greek word, the main idea), in the gold accent.

## Thumbnails

- One clear image, readable on a phone: a single striking visual from the video plus 2 to 4 words maximum.
- High contrast; the gold accent on a dark image works well for the brand.
- Vary composition between episodes; never reuse a template exactly.
- Make 3 options per video; log which one was chosen and its CTR.
