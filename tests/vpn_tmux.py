"""Exercise the bundled UI with a fake CLI in an isolated tmux server."""
import json
import os
import shutil
from pathlib import Path
import subprocess
import tempfile
import time

panel_source = Path(__file__).resolve().parents[1]/'components/apps/bin/atlas-vpn'
sock = 'atlas-vpn-test-'+str(os.getpid())
def tm(*args):
    return subprocess.check_output(['tmux','-L',sock,*args],text=True).strip()
def wait(check):
    for _ in range(60):
        result=check()
        if result:return result
        time.sleep(.1)
    raise AssertionError('Timed out')
for presentation in ('classic', 'framed'):
    with tempfile.TemporaryDirectory() as d:
        binary=Path(d)/'nym-vpnc'
        log=Path(d)/'commands'
        service_state=Path(d)/'service.json'
        service_log=Path(d)/'service-actions'
        app_log=Path(d)/'app-launches'
        service_state.write_text(json.dumps({'LoadState':'loaded', 'ActiveState':'active',
                                           'SubState':'running', 'UnitFileState':'enabled'}))
        systemctl=Path(d)/'systemctl'
        systemctl.write_text('''#!/usr/bin/env python3
import json, pathlib, sys
state_path=pathlib.Path(%r)
state=json.loads(state_path.read_text())
args=sys.argv[1:]
if 'show' in args:
 for key,value in state.items(): print(key+'='+value)
 sys.exit(0)
with open(%r,'a') as output: output.write(json.dumps(args)+'\\n')
if 'start' in args or 'enable' in args:
 state.update(ActiveState='active', SubState='running')
 if 'enable' in args: state['UnitFileState']='enabled'
 state_path.write_text(json.dumps(state))
else: sys.exit(2)
''' % (str(service_state), str(service_log)))
        systemctl.chmod(0o755)
        sudo=Path(d)/'sudo'
        sudo.write_text('''#!/usr/bin/env python3
import os, sys
args=sys.argv[1:]
if args and args[0]=='--': args=args[1:]
assert args and args[0]==%r, args
os.execv(%r, [%r, *args[1:]])
''' % (str(systemctl), str(systemctl), str(systemctl)))
        sudo.chmod(0o755)
        app=Path(d)/'nym-vpn-app'
        app.write_text('#!/usr/bin/env python3\nfrom pathlib import Path\np=Path(%r)\np.write_text(p.read_text()+"opened\\n" if p.exists() else "opened\\n")\n' % str(app_log))
        app.chmod(0o755)
        # Production uses fixed executables. Only this disposable copy substitutes
        # fixtures, so this integration test cannot reach the real service or GUI.
        source=panel_source.read_text()
        # Fix only the disposable copy's layout; never inherit the user's preference.
        source=source.replace('\nROW_ROLES =', '\nread_layout_style = lambda: ' + repr(presentation) + '\nROW_ROLES =', 1)
        heading = '// N Y M' if presentation == 'classic' else 'N Y M V P N'
        leading = 'SERVICE  active' if presentation == 'classic' else 'ACTIVE TUNNEL MODE'
        for name, real_path, fake_path in [('SYSTEMCTL','/usr/bin/systemctl',systemctl),
                                          ('SUDO','/usr/bin/sudo',sudo),
                                          ('NYM_APP','/usr/bin/nym-vpn-app',app)]:
            declaration=f'{name} = {real_path!r}'
            assert source.count(declaration)==1, declaration
            source=source.replace(declaration, f'{name} = {str(fake_path)!r}')
        runtime=Path(d)/'components/apps'
        (runtime/'bin').mkdir(parents=True)
        shutil.copy2(panel_source.parents[1]/'atlas_panel.py', runtime/'atlas_panel.py')
        panel=runtime/'bin/atlas-vpn'
        panel.write_text(source)
        panel.chmod(0o755)
        panel=str(panel)
        binary.write_text('''#!/usr/bin/env python3
import sys
state='Disconnected'
mode='on'
ipv6='on'
print('$ ',end='',flush=True)
for line in sys.stdin:
 c=line.strip()
 with open(%r,'a') as f:f.write(c+'\\n')
 if c=='connect':state='Connected'
 if c=='disconnect':state='Disconnected'
 if c.startswith('tunnel set --ipv6 '):ipv6=c.rsplit(' ',1)[1]
 if c.startswith('tunnel set --two-hop '):mode=c.rsplit(' ',1)[1]
 if c=='status':print('State: '+state)
 elif c=='tunnel get':print('IPv6: '+ipv6+'\\nTwo-hop: '+mode+'\\nNetstack: off\\nCircumvention transports: off\\nMixnet traffic configuration: poisson_parameter_for_loop_cover_stream: None, average_packet_delay: None, message_sending_average_delay: None, disable_poisson_rate: false, disable_background_cover_traffic: false')
 elif c=='gateway get':print('Entry point: Auto\\nExit point: Auto')
 print('$ ',end='',flush=True)
''' % str(log))
        binary.chmod(0o755)
        try:
            tm('-f','/dev/null','new-session','-d','-s','test','-x','200','-y','40','sleep 120')
            tm('set-environment','-g','PATH',d+':'+os.environ['PATH'])
            origin=tm('display-message','-p','-t','test:0','#{pane_id}')
            tm('run-shell','-t',origin,panel+' --toggle '+origin)
            wait(lambda:len(tm('list-panes','-t','test:0').splitlines())==2)
            vpn=tm('list-panes','-t','test:0','-F','#{pane_id} #{@atlas_vpn}').splitlines()[-1].split()[0]
            capture=lambda:tm('capture-pane','-p','-t',vpn)
            wait(lambda:'State: Disconnected' in capture())
            assert tm('display-message','-p','-t',vpn,'#{pane_width}')=='60'
            wait(lambda: (view := capture()) and all(hint in view for hint in
                 (heading, 'q close', 'Closing keeps VPN running')))
            if presentation == 'framed':
                view = capture()
                assert all(edge in view for edge in ('┌', '┐', '└', '┘'))
                assert '│ CONNECTION' in view and 'ACTIVE TUNNEL MODE' in view
                assert 'NEXT CONNECTION / CONFIGURATION' in view
            tm('resize-window','-t','test:0','-y','24')
            tm('resize-pane','-t',vpn,'-x','48')
            wait(lambda:tm('display-message','-p','-t',vpn,'#{pane_width}')=='48')
            hints=(heading, 'q close · c connect · d disconnect', 'm mode', 's settings', 'r refresh', 'i details', 'b setup', 'o app',
                   'Closing keeps VPN running')
            wait(lambda: (view := capture()) and all(hint in view for hint in hints))
            tm('send-keys','-t',vpn,'-N','50','j')
            wait(lambda: (view := capture()) and leading not in view
                 and heading in view and 'q close' in view)
            tm('send-keys','-t',vpn,'-N','50','k')
            wait(lambda:leading in capture())
            tm('resize-window','-t','test:0','-y','40')
            tm('resize-pane','-t',vpn,'-x','60')
            tm('send-keys','-t',vpn,'c')
            wait(lambda:'State: Connected' in capture())
            tm('send-keys','-t',vpn,'m')
            wait(lambda:'SELECT MODE' in capture())
            tm('send-keys','-t',vpn,'2')
            wait(lambda:'MIXNET / SETTINGS' in capture())
            tm('send-keys','-t',vpn,'a')
            wait(lambda:'Background cover traffic: on' in capture())
            tm('send-keys','-t',vpn,'1')
            wait(lambda:'Milliseconds:' in capture())
            tm('send-keys','-t',vpn,'Escape')
            tm('send-keys','-t',vpn,'Escape')
            tm('send-keys','-t',vpn,'Escape')
            wait(lambda:'SELECTED MODE   MIXNET' in capture())
            tm('send-keys','-t',vpn,'M')
            wait(lambda:'SELECT MODE' in capture())
            tm('send-keys','-t',vpn,'1')
            wait(lambda:'dVPN / SETTINGS' in capture())
            tm('send-keys','-t',vpn,'1')
            wait(lambda:'IPv6: off' in capture())
            tm('send-keys','-t',vpn,'1')
            wait(lambda:'IPv6: on' in capture())
            tm('send-keys','-t',vpn,'Escape')
            wait(lambda:'SELECTED MODE   dVPN' in capture())
            tm('send-keys','-t',vpn,'d')
            wait(lambda:log.read_text().count('disconnect')==1 and 'State: Disconnected' in capture())
            if presentation == 'framed':
                assert 'DISCONNECTED · NO ACTIVE TUNNEL' in capture()
            tm('run-shell','-t',origin,panel+' --toggle '+origin)
            assert len(tm('list-panes','-t','test:0').splitlines())==1
            tm('resize-window','-t','test:0','-x','100','-y','30')
            tm('run-shell','-t',origin,panel+' --toggle '+origin)
            wait(lambda:len(tm('list-windows','-t','test').splitlines())==2)
            vpn=tm('list-panes','-t','test:1','-F','#{pane_id}')
            wait(lambda:'State: Disconnected' in capture())
            tm('send-keys','-t',vpn,'q')
            wait(lambda:len(tm('list-windows','-t','test').splitlines())==1)
            assert log.read_text().count('disconnect')==1, 'Closing must not disconnect'
            tm('run-shell','-t',origin,panel+' --toggle '+origin)
            wait(lambda:len(tm('list-windows','-t','test').splitlines())==2)
            tm('run-shell','-t',origin,panel+' --toggle '+origin)
            assert len(tm('list-windows','-t','test').splitlines())==1
            assert not service_log.exists(), 'Opening/closing must not change service state'
            assert not app_log.exists(), 'Opening/closing must not launch the app'
            service_state.write_text(json.dumps({'LoadState':'loaded', 'ActiveState':'inactive',
                                               'SubState':'dead', 'UnitFileState':'disabled'}))
            tm('run-shell','-t',origin,panel+' --toggle '+origin)
            wait(lambda:len(tm('list-windows','-t','test').splitlines())==2)
            vpn=tm('list-panes','-t','test:1','-F','#{pane_id}')
            wait(lambda:'SERVICE & ACCOUNT SETUP' in capture())
            tm('send-keys','-t',vpn,'2')
            wait(lambda:'confirm' in capture().lower())
            tm('send-keys','-t',vpn,'Escape')
            time.sleep(.2)
            assert not service_log.exists(), 'Cancelling setup must not mutate service'
            assert not app_log.exists(), 'Cancelling setup must not launch the app'
            tm('send-keys','-t',vpn,'2')
            wait(lambda:'confirm' in capture().lower())
            tm('send-keys','-t',vpn,'y')
            wait(lambda:app_log.exists())
            actions=[json.loads(line) for line in service_log.read_text().splitlines()]
            assert len(actions)==1 and 'enable' in actions[0] and '--now' in actions[0], actions
            assert actions[0][-1]=='nym-vpnd.service', actions
            assert json.loads(service_state.read_text())['UnitFileState']=='enabled'
            tm('send-keys','-t',vpn,'o')
            wait(lambda:app_log.read_text().count('opened')==2)
            assert len(service_log.read_text().splitlines())==1
            tm('run-shell','-t',origin,panel+' --toggle '+origin)
            commands=log.read_text().splitlines()
            assert commands.count('connect')==commands.count('disconnect')==1, 'Setup must not send tunnel connect/disconnect'
            print(f'PASS: {presentation} panel controls, close preserves tunnel, service setup confirmation/readback/app launch')
        finally:
            tm('kill-server')
