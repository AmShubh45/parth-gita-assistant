The stream's working folder (mounted into Docker as /app/data). It keeps:
  cache/      every voice recording, made once and reused for ever
  state.json  where the recitation is, so a restart resumes there
  token.json  the YouTube sign-in (copy it here from the PC where you ran youtube_auth.py)
  music.mp3   optional background music you have the rights to stream
  logs/       live.log
Nothing here is committed to git.
