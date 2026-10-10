"""Generate source-contained TrueNAS YAML; no repo or registry upload needed."""
from pathlib import Path
import copy
import base64
import gzip
import json
import yaml

root = Path(__file__).resolve().parent.parent

class Literal(str):
    pass

yaml.SafeDumper.add_representer(Literal, lambda dumper, value: dumper.represent_scalar('tag:yaml.org,2002:str', value, style='|'))

def embedded(name, target):
    # Keep JSON-encoded app.create/app.update requests below TrueNAS's 64 KiB
    # limit. Decode the exact source during the build; no external upload needed.
    source = (root / name).read_bytes()
    packed = base64.b64encode(gzip.compress(source, mtime=0)).decode('ascii')
    return f"RUN printf '%s' '{packed}' | base64 -d | gzip -d > {target}\n"

dockerfile = (root / 'Dockerfile').read_text()
dockerfile = '# syntax=docker/dockerfile:1\n' + dockerfile
for old, new in [
    ('COPY bridge-calendar-api.go /src/cmd/carbonate/calendar_api.go\n', embedded('bridge-calendar-api.go', '/src/cmd/carbonate/calendar_api.go')),
    ('COPY bridge-calendar-query.go /src/internal/calendar/query.go\n', embedded('bridge-calendar-query.go', '/src/internal/calendar/query.go')),
    ('COPY carbonate-cli.patch /tmp/carbonate-cli.patch\n', embedded('carbonate-cli.patch', '/tmp/carbonate-cli.patch')),
    ('COPY requirements.txt .\n', embedded('requirements.txt', '/app/requirements.txt')),
    ('COPY app.py calendar_operations.py claude_connector.py entrypoint.sh ./\n', embedded('app.py', '/app/app.py') + embedded('calendar_operations.py', '/app/calendar_operations.py') + embedded('claude_connector.py', '/app/claude_connector.py') + embedded('entrypoint.sh', '/app/entrypoint.sh') + embedded('bootstrap.py', '/app/bootstrap.py')),
]:
    assert old in dockerfile
    dockerfile = dockerfile.replace(old, new)
base = yaml.safe_load((root / 'compose.yaml').read_text())
base.pop('secrets')
calendar = base['services']['calendar']
calendar.pop('image')
calendar['pull_policy'] = 'build'
calendar['build'] = {'context': '.', 'dockerfile_inline': Literal(dockerfile.replace('$', '$$'))}
calendar['command'] = ['python', '/app/bootstrap.py']
calendar.pop('secrets')
calendar['environment'] = {
    'DATA_DIR': '/data', 'PUBLIC_URL': 'https://YOUR_PUBLIC_HOST',
    'CALENDAR_TIMEZONE': 'Europe/Helsinki', 'DEFAULT_DURATION_MINUTES': '60', 'PROTON_CALENDAR_ID': '',
    'ACTION_API_KEY': 'REPLACE_WITH_A_RANDOM_KEY_OF_AT_LEAST_32_CHARACTERS',
    'CARBONATE_BRIDGE_PASSWORD_FILE': '/data/bridge_password', 'CARBONATE_NO_INVITATIONS': '1',
    'PROTON_USERNAME': '', 'PROTON_PASSWORD': '', 'PROTON_TWO_FACTOR_CODE': '',
    'PROTON_MAILBOX_PASSWORD': '', 'PROTON_LOGIN_ATTEMPT': '1',
}
calendar['volumes'] = ['calendar_data:/data']
calendar['depends_on'] = {'initialize-storage': {'condition': 'service_completed_successfully'}}
base['services']['initialize-storage'] = {
    'image': 'python:3.14-slim-bookworm', 'user': '0:0', 'restart': 'no',
    'command': ['python', '-c', 'import os; os.chown("/data", 10001, 10001); os.chmod("/data", 0o700)'],
    'volumes': ['calendar_data:/data'], 'network_mode': 'none',
    'read_only': True, 'cap_drop': ['ALL'], 'cap_add': ['CHOWN', 'FOWNER'],
    'security_opt': ['no-new-privileges:true'],
}
base['volumes'] = {'calendar_data': {}}
header = '# Self-contained TrueNAS Apps YAML: paste ONE file. No SSH, uploaded source, or prebuilt image required.\n# Set environment values under calendar; keep the build/source block intact.\n# See truenas/README.md for login, 2FA and connection instructions.\n'
(root / 'truenas/existing-proxy.yaml').write_text(header + yaml.safe_dump(base, sort_keys=False))
ddns = copy.deepcopy(base)
proxy = yaml.safe_load((root / 'compose.ddns.yaml').read_text())
caddy = proxy['services']['caddy']
caddy['environment']['CALENDAR_DOMAIN'] = 'YOUR_PUBLIC_HOST'
caddy['volumes'] = ['caddy_data:/data', 'caddy_config:/config']
caddy['configs'] = [{'source': 'caddyfile', 'target': '/etc/caddy/Caddyfile'}]
ddns['services']['caddy'] = caddy
ddns['volumes'].update({'caddy_data': {}, 'caddy_config': {}})
ddns['configs'] = {'caddyfile': {'content': Literal((root / 'Caddyfile').read_text().replace('$', '$$'))}}
(root / 'truenas/ddns.yaml').write_text(header + yaml.safe_dump(ddns, sort_keys=False))
funnel = copy.deepcopy(base)
funnel['services']['calendar'].pop('ports')
funnel['services']['calendar']['network_mode'] = 'service:tailscale'
funnel['services']['calendar']['depends_on']['tailscale'] = {'condition': 'service_started'}
ts = yaml.safe_load((root / 'compose.funnel.yaml').read_text())['services']['tailscale']
ts.pop('env_file')
ts['environment']['TS_AUTHKEY'] = 'REPLACE_WITH_YOUR_TAILSCALE_AUTH_KEY'
ts['volumes'] = ['tailscale_state:/var/lib/tailscale']
ts['configs'] = [{'source': 'tailscale_serve', 'target': '/config/serve.json'}]
funnel['services']['tailscale'] = ts
funnel['volumes']['tailscale_state'] = {}
funnel['configs'] = {'tailscale_serve': {'content': Literal((root / 'tailscale/serve.json').read_text().replace('$', '$$'))}}
(root / 'truenas/funnel.yaml').write_text(header + yaml.safe_dump(funnel, sort_keys=False))

# JSON adds escaping around the YAML. Reserve headroom for private settings and
# the UI request envelope, rather than checking only the YAML file size.
for name in ('existing-proxy', 'ddns', 'funnel'):
    text = (root / f'truenas/{name}.yaml').read_text()
    if len(json.dumps(text).encode()) > 48000:
        raise ValueError(f'{name} YAML exceeds the TrueNAS request size budget')
