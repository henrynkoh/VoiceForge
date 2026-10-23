# Series brief (paste this at the top of every per-title session)

Copy this file verbatim as the first message of each new session, fill the two placeholders, and add one line naming the title. Identical opening text is what makes DeepSeek's prefix cache pay off: after the first session, this brief costs almost nothing.

---

PROJECT: VoiceForge series run.
BRIEF VERSION: 1. Do not restate this brief back to me.

WHAT WE ARE DOING
Building title {{TITLE_N}} of {{TITLE_TOTAL}} in the series "{{SERIES_NAME}}", for the Rightly Dividing channel. The series plan, titles, descriptions and hashtags already exist in SERIES.md. Do not redesign the series; execute one title.

VOICE AND ENGINE
- Free local clone: voice id `henry-local`, engine `voicebox`, model chosen automatically (LuxTTS today), pace already fixed at 13.3 chars/s.
- Cloud clone: voice id `henry-rd`, engine `elevenlabs`, used only for Korean text and for stings that quote scripture.
- English narration is free. Never send English body text to the cloud.

FILES AND COMMAND SHAPES
- Project root: ~/Documents/Claude/Projects/voiceforge
- Series folder: audiobooks/series/{{SERIES_SLUG}}/
- This title's script: audiobooks/series/{{SERIES_SLUG}}/scripts/{{TITLE_N}}-{{TITLE_SLUG}}.md
- Render: python3 tools/series.py render {{TITLE_N}}
- Upload as private draft: python3 tools/series.py upload {{TITLE_N}}
- Status of every title: python3 tools/series.py status

RULES THAT ARE NOT NEGOTIABLE
- King James Version quotations only, quoted exactly, verified against a KJV text source before rendering. If a verse cannot be verified, say so instead of guessing.
- No invented numbers. If something is unmeasured, say it is unmeasured.
- Report only: duration, defects, credits spent, file paths. No pasting of file contents or long tool output.
- Stop when the title is rendered and uploaded. Do not start the next title in this session.

STATE
Everything you learn that matters goes into PROJECT_STATE.md in one or two lines, so the next session starts from that file rather than from this conversation.

TASK FOR THIS SESSION
{{ONE_OR_TWO_SENTENCES_DESCRIBING_THIS_TITLE_ONLY}}
