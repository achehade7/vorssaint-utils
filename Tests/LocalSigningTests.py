#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Vorssaint
"""Exercise signing search-list cleanup and preservation without real keychains."""
from pathlib import Path
import json
import os
import subprocess
import tempfile

repo = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='local-signing-tests-') as temporary:
    root = Path(temporary)
    home = root / 'home'
    kc = home / 'Library/Keychains/vorssaint-signing.keychain-db'
    kc.parent.mkdir(parents=True)
    kc.write_bytes(b'identity must survive a failed probe')
    commands = root / 'bin'
    commands.mkdir()
    state = root / 'search-list.json'
    log = root / 'commands.jsonl'
    stub = '''#!/usr/bin/env python3
import json,os,sys,signal
from pathlib import Path
state=Path(os.environ['STATE']); log=Path(os.environ['LOG'])
args=sys.argv[1:]; command=Path(sys.argv[0]).name
with log.open('a') as f: f.write(json.dumps([command,*args])+'\\n')
if command=='security':
 if args[0]=='unlock-keychain': sys.exit(int(os.environ.get('UNLOCK_FAIL','0')))
 if args[0]=='list-keychains':
  if '-s' in args: state.write_text(json.dumps(args[args.index('-s')+1:]))
  else:
   for item in json.loads(state.read_text()): print('    "'+item+'"')
 else: raise AssertionError('unexpected keychain mutation: '+str(args))
else:
 kc=str(Path.home()/'Library/Keychains/vorssaint-signing.keychain-db')
 values=json.loads(state.read_text()); assert kc in values
 if os.environ.get('ADD_OTHER'): state.write_text(json.dumps(values+['another.keychain']))
 if os.environ.get('TERMINATE'): os.kill(os.getppid(),signal.SIGTERM)
 sys.exit(int(os.environ.get('SIGN_FAIL','0')))
'''
    for name in ['security', 'codesign']:
        path = commands / name
        path.write_text(stub)
        path.chmod(0o700)
    env = {**os.environ, 'HOME': str(home), 'PATH': str(commands)+':'+os.environ['PATH'],
           'STATE': str(state), 'LOG': str(log)}
    checks = 0
    for extras, initial, expected_exit in [
        ({}, ['login.keychain'], 0),
        ({'SIGN_FAIL':'7'}, ['login.keychain'], 7),
        ({'UNLOCK_FAIL':'3'}, ['login.keychain'], 3),
        ({}, ['login.keychain',str(kc)], 0),
        ({'ADD_OTHER':'1'}, ['login.keychain'], 0),
        ({'TERMINATE':'1'}, ['login.keychain'], 143),
    ]:
        state.write_text(json.dumps(initial))
        result = subprocess.run(['zsh', str(repo/'Tools/codesign-local.sh'), '--sign', 'fixture', 'probe'],
                                env={**env, **extras}, capture_output=True, text=True, timeout=10)
        assert result.returncode == expected_exit, result.stderr
        expected = initial + (['another.keychain'] if 'ADD_OTHER' in extras else [])
        assert json.loads(state.read_text()) == expected
        checks += 2
    state.write_text(json.dumps(['login.keychain']))
    original = kc.read_bytes()
    result = subprocess.run(['zsh', str(repo/'Tools/setup-signing.sh')],
                            env={**env,'SIGN_FAIL':'7'}, capture_output=True,text=True,timeout=10)
    assert result.returncode == 1 and 'Preserved' in result.stderr, result.stderr
    assert kc.read_bytes() == original
    assert json.loads(state.read_text()) == ['login.keychain']
    assert not any(json.loads(line)[1] in ['delete-keychain','create-keychain','import']
                   for line in log.read_text().splitlines())
    checks += 4
    print(f'PASS: {checks} local signing safety checks')
