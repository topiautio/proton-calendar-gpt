"""Create local secret files without printing secrets; run on the NAS with sudo."""
import os
import secrets
from pathlib import Path

root = Path(__file__).resolve().parent
for name in ("data", "secrets"):
    path = root / name
    path.mkdir(mode=0o700, exist_ok=True)
    if os.geteuid() == 0:
        os.chown(path, 10001, 10001)
    path.chmod(0o700)
for name, value in (("action_api_key", secrets.token_urlsafe(48)), ("bridge_password", "")):
    path = root / "secrets" / name
    if not path.exists():
        path.write_text(value + "\n")
        if os.geteuid() == 0:
            os.chown(path, 10001, 10001)
        path.chmod(0o600)
env = root / ".env"
if not env.exists():
    env.write_text((root / ".env.example").read_text())
    env.chmod(0o600)
print("Created data/, secrets/ and .env; existing files were preserved.")
if os.geteuid() != 0:
    print("On TrueNAS, ensure UID 10001 can write data/ and read both secret files.")
