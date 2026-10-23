# Project state

The one file a fresh session reads to become productive in a single turn. Update it at the end of every title, in one or two lines per item. If it is not in here, the next session will pay tokens to rediscover it.

## Decisions that are settled

- Voice: `henry-local` (voicebox, free) for English body text; `henry-rd` (elevenlabs) for Korean and scripture-critical stings.
- Pace fix: LuxTTS renders at `speed 0.72`, which measures 13.3 characters per second, matching the speaker.
- Chunk ceiling: 400 characters on LuxTTS. Larger chunks kill the 3.8 GB container.
- Render serially. Parallel renders caused out-of-memory kills.
- Scripture: KJV only, quoted exactly, verified against a KJV text source before the audio is rendered.

## Files that exist

| path | what it is |
|---|---|
|  |  |

## Rendered and measured

| title | duration | defects | credits | file | video id |
|---|---|---|---|---|---|
|  |  |  |  |  |  |

## Pending

- [ ] 

## Known issues and how they were fixed

- 

## Next step (one line)

- 
