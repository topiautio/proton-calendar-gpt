import subprocess

import bootstrap


def credentials(monkeypatch):
    monkeypatch.setenv('PROTON_USERNAME', 'test-user')
    monkeypatch.setenv('PROTON_PASSWORD', 'private-password')
    monkeypatch.setenv('PROTON_TWO_FACTOR_CODE', '123456')
    monkeypatch.setenv('PROTON_LOGIN_ATTEMPT', '1')
    monkeypatch.delenv('PROTON_MAILBOX_PASSWORD', raising=False)


def test_bridge_secret_persists_and_is_private(tmp_path, monkeypatch):
    monkeypatch.setenv('CARBONATE_BRIDGE_PASSWORD', 'unused')
    bootstrap.initialize_bridge(tmp_path)
    secret = (tmp_path / 'bridge_password').read_text()
    bootstrap.initialize_bridge(tmp_path)
    assert (tmp_path / 'bridge_password').read_text() == secret
    assert (tmp_path / 'bridge_password').stat().st_mode & 0o777 == 0o600
    assert bootstrap.os.environ['CARBONATE_BRIDGE_PASSWORD'] == secret.strip()


def test_failed_login_not_repeated_or_logged(tmp_path, monkeypatch, capsys):
    credentials(monkeypatch)
    calls = []
    def fail(args, **kwargs):
        calls.append(args)
        assert kwargs['input'] == b'private-password\n123456\n'
        assert kwargs['capture_output'] is True
        return subprocess.CompletedProcess(args, 1, b'private-password', b'private-token')
    monkeypatch.setattr(bootstrap.subprocess, 'run', fail)
    assert not bootstrap.login_once(tmp_path)
    assert not bootstrap.login_once(tmp_path)
    assert len(calls) == 1
    output = capsys.readouterr().err
    assert 'private-password' not in output and 'private-token' not in output
    monkeypatch.setenv('PROTON_LOGIN_ATTEMPT', '2')
    assert not bootstrap.login_once(tmp_path)
    assert len(calls) == 2


def test_existing_session_does_not_log_in_again(tmp_path, monkeypatch):
    credentials(monkeypatch)
    (tmp_path / 'auth.json').write_text('fake encrypted session')
    def unexpected(*args, **kwargs):
        raise AssertionError('must not reauthenticate an existing session')
    monkeypatch.setattr(bootstrap.subprocess, 'run', unexpected)
    assert bootstrap.login_once(tmp_path)
    assert not bootstrap.login_once(tmp_path, interactive=True)


def test_success_keeps_generated_bridge_password(tmp_path, monkeypatch):
    credentials(monkeypatch)
    def success(args, **kwargs):
        assert '-password-stdin' in args
        assert '-keep-bridge-password' in args
        assert 'private-password' not in args
        (tmp_path / 'auth.json').write_text('fake encrypted session')
        return subprocess.CompletedProcess(args, 0, b'', b'')
    monkeypatch.setattr(bootstrap.subprocess, 'run', success)
    assert bootstrap.login_once(tmp_path)
