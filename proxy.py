import socket, threading, select, sys, urllib.request, ssl

def handle(c):
    try:
        c.settimeout(5)
        d = b''
        while b'\r\n\r\n' not in d:
            chunk = c.recv(4096)
            if not chunk:
                return
            d += chunk
            if len(d) > 65536:
                break
        sys.stderr.write("RECEIVED: " + repr(d[:200]) + "\n")
        sys.stderr.flush()
        fl = d.split(b'\r\n')[0].decode('utf-8', errors='replace')
        parts = fl.split()
        sys.stderr.write("PARTS: " + repr(parts) + "\n")
        sys.stderr.flush()
        
        if len(parts) >= 2 and parts[0].upper() == 'CONNECT':
            host_port = parts[1]
            host, port = host_port.rsplit(':', 1)
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
                        if not chunk:
                            return
                        if s is c:
                            r.sendall(chunk)
                        else:
                            c.sendall(chunk)
            except Exception as e:
                sys.stderr.write("CONNECT ERR: " + str(e) + "\n")
                sys.stderr.flush()
                try:
                    c.sendall(b'HTTP/1.1 502 Bad Gateway\r\n\r\n' + str(e).encode())
                except:
                    pass
        elif len(parts) >= 2 and parts[0].upper() == 'GET':
            url = parts[1]
            sys.stderr.write("URL: " + url + "\n")
            sys.stderr.flush()
            if url.startswith('http://'):
                host = url.split('/')[2]
            elif url.startswith('https://'):
                host = url.replace('https://', '').split('/')[0]
            else:
                host = '127.0.0.1'
            sys.stderr.write("HOST: " + host + "\n")
            sys.stderr.flush()
            try:
                remote = socket.create_connection((host, 80), timeout=15)
                remote.sendall(d)
                socks = [c, remote]
                while True:
                    rd, _, _ = select.select(socks, [], [])
                    for s in rd:
                        chunk = s.recv(4096)
                        if not chunk:
                            return
                        if s is c:
                            remote.sendall(chunk)
                        else:
                            c.sendall(chunk)
            except Exception as e:
                sys.stderr.write("GET ERR: " + str(e) + "\n")
                sys.stderr.flush()
                try:
                    c.sendall(b'HTTP/1.1 502 Bad Gateway\r\n\r\n' + str(e).encode())
                except:
                    pass
        else:
            sys.stderr.write("UNKNOWN: " + fl + "\n")
            sys.stderr.flush()
            try:
                c.sendall(b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK')
            except:
                pass
    except Exception as e:
        sys.stderr.write("HANDLE ERR: " + str(e) + "\n")
        sys.stderr.flush()
    finally:
        try:
            c.close()
        except:
            pass

srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(('0.0.0.0', 8888))
srv.listen(5)
sys.stderr.write("PROXY READY on port 8888\n")
sys.stderr.flush()
while True:
    c, _ = srv.accept()
    threading.Thread(target=handle, args=(c,)).start()
