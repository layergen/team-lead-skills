"""Copy tools/teamdata.py into every skill, so each skill folder works on its own."""
import pathlib
import shutil

ROOT = pathlib.Path(__file__).resolve().parent.parent
for skill in sorted((ROOT / "skills").iterdir()):
    if (skill / "SKILL.md").exists():
        shutil.copyfile(ROOT / "tools" / "teamdata.py", skill / "teamdata.py")
        print("synced", skill.name)
