# StudyBuddyAI — Cinematic Studyverse Upgrade

This build preserves the existing Streamlit study app and adds a dependency-free cinematic interaction layer.

## Features added
- Multi-mood animated background: Nebula, Aurora, Solar flare, Eclipse
- Interactive star particles, soft nebula lighting, pointer parallax and nearby constellation filaments
- Cursor aura, subtle sparkles and celebratory bursts on relevant interactions
- Discreet toast notifications for app success messages
- Distraction-free focus overlay with a 25-minute timer, pause/resume and reset
- Keyboard shortcuts: **F** focus mode, **P** pause/resume while focus mode is open, **Esc** close focus mode, **?** shortcut help
- Calm mode and respects the browser's reduced-motion preference
- Responsive controls for small screens
- Existing ambient synth control, galaxy scenery, study features, and local browser store retained

## Files to keep together
- `app.py`
- `study_data.json`
- `requirements.txt`
- `SETUP_GLOBAL_LOBBY.sql`
- `assets/studybuddy_motion.css`
- `assets/studybuddy_motion.js`
- `components/local_store/index.html`

## Deploy on Streamlit Community Cloud
1. Back up your current repository first.
2. Upload the files and folders above, preserving their paths.
3. Keep your existing Streamlit secrets and Supabase setup as-is; do not paste secret keys into Python source.
4. Commit the changes and let Streamlit rebuild.

The Python file is syntax-checked, and the JavaScript engine passes a syntax check. It has not been tested against your live Streamlit deployment, browser, or Supabase instance, so verify the deployed app before deleting your backup.

## About file size
The code intentionally avoids padding the project to an arbitrary 1 MB. Its effects are real procedural animations and interactions; adding unused code would slow maintenance without improving the experience.
