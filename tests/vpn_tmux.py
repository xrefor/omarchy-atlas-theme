"""Exercise the bundled UI with a fake CLI in an isolated tmux server."""
import os
from pathlib import Path
import subprocess
import tempfile
import time

panel = str(Path(__file__).resolve().parents[1]/'components/apps/bin/atlas-vpn')
sock = 'atlas-vpn-test-'+str(os.getpid())
def tm(*args):
    return subprocess.check_output(['tmux','-L',sock,*args],text=True).strip()
def wait(check):
    for _ in range(60):
        result=check()
        if result:return result
        time.sleep(.1)
    raise AssertionError('Timed out')
with tempfile.TemporaryDirectory() as d:
    binary=Path(d)/'nym-vpnc'
    log=Path(d)/'commands'
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
        print(capture())
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
        print('PASS: wide toggle, narrow toggle, controls, q leaves connection unchanged')
    finally:
        tm('kill-server')
