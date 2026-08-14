# Competition Demo Fixture

This directory contains the preloaded fixture used when
`COMPETITION_DEMO_MODE=true`.

- The MP4 is a project-generated FFmpeg test pattern with silent audio. It
  contains no third-party footage or audio.
- Subtitle, Summary, and Q&A text reuse existing automated-test fixtures from
  this repository. They are preloaded results, not a live DeepSeek response.
- Runtime edits are written to the ignored `data/` workspace. The immutable
  fixture files in this directory are not modified by the application.
- No API key, provider request/response, prompt log, user data, or personal path
  is stored here.
