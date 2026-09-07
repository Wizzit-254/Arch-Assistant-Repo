#!/usr/bin/env python3
import socket, threading, select, sys

def handle(c):
    try:
        c.settimeout(5)
        d = b''
        while b'\r\n\r\n' not in d:
            chunk = c.recv(4096)
            if not chunk: return
            d += chunk
            if len(d) > 8192: break
        # Log what we receive
        sys.stderr.write("RECEIVED: " + d[:500].decode('utf-8', errors='replace') + "\n")
        sys.stderr.flush()
        fl = d.split(b'\r\n')[0].decode('utf-8', errors='replace')
        p = fl.split()
        if len(p) >= 2 and p[0].upper() == 'CONNECT':
            hp = p[1]
            host, port = hp.rsplit(':', 1)
            port = int(port)
            try:
                r = socket.create_connection((host, port), timeout=15)
                c.sendall(b'HTTP/1.1 200 Connection established\r\n\r\n')
                c.settimeout(None)
                socks = [c, r]
                while True:
                    rd, _, _ = select.select(socks, [], [])
                    for s in rd:
                        chunk = s.recv(4096)
                        if not chunk: return
                        if s is c: r.sendall(chunk)
                        else: c.sendall(chunk)
            except Exception as e:
                try: c.sendall(b'HTTP/1.1 502 Bad Gateway\r\n\r\n' + str(e).encode())
                except: pass
        else:
            try:
                if parts[0].upper() == 'GET':
                    url = parts[1]
                    if url.startswith('http://'):
                        host = url.split('/')[2]
                    else:
                        host = '127.0.0.1'
                    port = 80
                    remote = socket.create_connection((host, port), timeout=15)
                    remote.sendall(d)
                    socks = [c, remote]
                    while True:
                        r, _, _ = select.select(socks, [], [])
                        for s in r:
                            chunk = s.recv(4096)
                            if not chunk: return
                            if s is c: remote.sendall(chunk)
                            else: c.sendall(chunk)
            except Exception as e:
                try: c.sendall(b'HTTP/1.1 502 Bad Gateway\r\n\r\n' + str(e).encode())
                except: pass
    except: pass
    finally:
        try: c.close()
        except: pass

srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(('0.0.0.0', 8888))
srv.listen(5)
while True:
    c, _ = srv.accept()
    threading.Thread(target=handle, args=(c,)).start()
