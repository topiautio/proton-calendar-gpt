"""Optional TrueNAS YAML startup: create a bridge secret and log in once."""
import os
import secrets
import subprocess
import sys
from pathlib import Path


def initialize_bridge(data):
    data.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = data / 'bridge_password'
    if not path.exists():
        with path.open('x') as out:
            out.write(secrets.token_urlsafe(48) + '\n')
    path.chmod(0o600)
    os.environ['CARBONATE_BRIDGE_PASSWORD_FILE'] = str(path)
    os.environ['CARBONATE_BRIDGE_PASSWORD'] = path.read_text().strip()


def login_once(data, interactive=False):
    if (data / 'auth.json').exists():
        if interactive:
            print('A session already exists. Stop calendar activity before reauthentication.', file=sys.stderr)
            return False
        return True
    username = os.getenv('PROTON_USERNAME', '')
    password = os.getenv('PROTON_PASSWORD', '')
    if not username or (not interactive and not password):
        print('Proton login is not configured. Set PROTON_USERNAME and PROTON_PASSWORD in the App YAML, or use the App container Shell for interactive login.', file=sys.stderr)
        return False
    args = ['carbonate', 'auth', username, '-session', str(data / 'auth.json'), '-keep-bridge-password']
    if interactive:
        return subprocess.run(args, check=False).returncode == 0
    attempt = os.getenv('PROTON_LOGIN_ATTEMPT', '1')
    marker = data / 'login_attempt'
    if marker.exists() and marker.read_text() == attempt:
        print('No automatic login retry. Update the credentials/code and increment PROTON_LOGIN_ATTEMPT in the App YAML to try once again.', file=sys.stderr)
        return False
    answers = [password]
    for name in ('PROTON_TWO_FACTOR_CODE', 'PROTON_MAILBOX_PASSWORD'):
        if os.getenv(name):
            answers.append(os.environ[name])
    if any('\n' in answer or '\r' in answer for answer in answers):
        print('Login answers must each be one line.', file=sys.stderr)
        return False
    marker.write_text(attempt)
    marker.chmod(0o600)
    try:
        # Keep login output and credentials out of App logs; manual challenges
        # can be handled interactively in the browser's container Shell.
        result = subprocess.run(args + ['-password-stdin'], input=('\n'.join(answers) + '\n').encode(), capture_output=True, timeout=120, check=False)
        success = result.returncode == 0 and (data / 'auth.json').exists()
    except (subprocess.TimeoutExpired, OSError):
        success = False
    print('Proton session configured.' if success else 'Proton login did not complete. Check credentials/2FA, or open the calendar container Shell and run: python /app/bootstrap.py --interactive-login', file=sys.stderr)
    return success


def main():
    os.umask(0o077)
    data = Path(os.getenv('DATA_DIR', '/data'))
    initialize_bridge(data)
    interactive = sys.argv[1:] == ['--interactive-login']
    if not interactive:
        key = os.getenv('ACTION_API_KEY', '')
        if len(key) < 32 or key.startswith('REPLACE_'):
            raise SystemExit('Set ACTION_API_KEY in the App YAML to a private random key of at least 32 characters.')
    success = login_once(data, interactive)
    if interactive:
        raise SystemExit(0 if success else 1)
    for name in ('PROTON_PASSWORD', 'PROTON_TWO_FACTOR_CODE', 'PROTON_MAILBOX_PASSWORD'):
        os.environ.pop(name, None)
    os.execvp('uvicorn', ['uvicorn', 'app:app', '--host', '0.0.0.0', '--port', '8000', '--workers', '1', '--no-access-log'])


if __name__ == '__main__':
    main()
