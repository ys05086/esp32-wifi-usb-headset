"""Check that a second Wi-Fi client cannot take over an active USB session."""
import ctypes, json, secrets, socket, struct, sys, time, urllib.request
host = sys.argv[1]
def stats():
    return json.load(urllib.request.urlopen('http://'+host+'/status', timeout=3))
def packet(session, seq, stop=False):
    return struct.pack('<4sIIHH', b'VSM1', session, seq, 0 if stop else 480, 1 if stop else 2)+(b'' if stop else bytes(960))
a=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);b=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
for s in [a,b]: s.connect((host,49152)); s.settimeout(.1)
sid=secrets.randbelow(2**32-2)+1
time.sleep(.4); before=stats()['received']; ctypes.windll.winmm.timeBeginPeriod(1)
try:
    for seq in range(60):
        a.send(packet(sid,seq)); time.sleep(.003); b.send(packet(sid+1,seq)); time.sleep(.007)
    first=stats()['received']-before
    assert first==60, ('owner accepted count', first)
    try: data=b.recv(2048); raise AssertionError(('contender got data',data[:4]))
    except socket.timeout: pass
    a.send(packet(sid,60,True)); time.sleep(.02)
    for seq in range(60,80): b.send(packet(sid+1,seq)); time.sleep(.01)
    second=stats()['received']-before-first
    assert second==20, ('handoff accepted count',second)
    print(json.dumps({'exclusive_owner_packets':first,'handoff_packets':second,'pass':True}))
finally:
    a.send(packet(sid,80,True));b.send(packet(sid+1,80,True));a.close();b.close();ctypes.windll.winmm.timeEndPeriod(1)
