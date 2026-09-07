#!/usr/bin/env python3
import socket, threading, select, sys, urllib.request, ssl

def handle_client(client):
    try:
        client.settimeout(5)
        data = b''
        while b'\r\n\r\n' not in data:
            chunk = client.recv(4096)
            if not chunk: return
            data += chunk
            if len(data) > 65536: break
        fl = data.split(b'\r\n')[0].decode('utf-8', errors='replace')
        parts = fl.split()
        sys.stderr.write("REQUEST: " + repr(fl[:200]) + "\n")
        sys.stderr.flush()
        
        if len(parts) >= 2 and parts[0].upper() == 'CONNECT':
            host_port = parts[1]
            host, port = host_port.rsplit(':', 1)
            port = int(port)
            try:
                r = socket.create_connection((host, port), timeout=15)
                client.sendall(b'HTTP/1.1 200 Connection established\r\n\r\n')
                client.settimeout(None)
                socks = [client, r]
                while True:
                    rd, _, _ = select.select(socks, [], [])
                    for s in rd:
                        chunk = s.recv(4096)
                        if not chunk: return
                        if s is client: r.sendall(chunk)
                        else: client.sendall(chunk)
            except Exception as e:
                try: client.sendall(b'HTTP/1.1 502 Bad Gateway\r\n\r\n' + str(e).encode())
                except: pass
        elif len(parts) >= 2 and parts[0].upper() in ('GET','POST','PUT','DELETE','HEAD'):
            method = parts[0].upper()
            url = parts[1].decode('utf-8', errors='replace')
            headers = {}
            for line in data.split(b'\r\n')[1:]:
                if b': ' in line:
                    k, v = line.split(b': ', 1)
                    k = k.decode('utf-8', errors='replace')
                    v = v.decode('utf-8', errors='replace')
                    if k.lower() not in ('proxy-connection', 'connect'):
                        headers[k] = v
            
            if url.startswith('https://') or url.startswith('http://'):
                if not url.startswith('http://'):
                    url = url.replace('https://', 'http://')
                try:
                    req = urllib.request.Request(url, headers={**headers, 'User-Agent': 'Mozilla/5.0'})
                    ctx = ssl.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                    resp = urllib.request.urlopen(req, timeout=15, context=ctx)
                    content = resp.read()
                    client.sendall(b'HTTP/1.1 200 OK\r\n')
                    ct = resp.headers.get('Content-Type','text/html')
                    client.sendall(f'Content-Type: {ct}\r\n'.encode())
                    client.sendall(f'Content-Length: {len(content)}\r\n'.encode())
                    client.sendall(b'Access-Control-Allow-Origin: *\r\n')
                    client.sendall(b'Connection: close\r\n')
                    client.sendall(b'\r\n')
                    client.sendall(content)
                except Exception as e:
                    try: client.sendall(b'HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n')
                    except: pass
            else:
                try: client.sendall(b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK')
                except: pass
        else:
            try: client.sendall(b'HTTP/1.1 200 OK\r\nContent-Length: -2\r\n\r\n')
            except: pass
    except: pass
    finally:
        try: client.close()
        except: pass

srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(('0.0.0.0', 8888))
srv.listen(5)
sys.stderr.write("PROXY READY on port 8888\n")
sys.stderr.flush()
while True:
    c, _ = srv.accept()
    threading.Thread(target=handle_client, args=(c,)).start()
