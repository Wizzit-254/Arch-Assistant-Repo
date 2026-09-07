import socket, threading, select, sys

def log(msg):
    sys.stderr.write(str(msg) + "\n")
    sys.stderr.flush()

def relay(a, b):
    try:
        socks = [a, b]
        while True:
            try:
                rd, _, _ = select.select(socks, [], [], 60)
            except:
                break
            for s in rd:
                try:
                    chunk = s.recv(8192)
                    if not chunk:
                        return
                    if s is a:
                        b.sendall(chunk)
                    else:
                        a.sendall(chunk)
                except:
                    return
    except:
        pass

def handle(c):
    try:
        c.settimeout(10)
        d = b''
        while b'\r\n\r\n' not in d:
            chunk = c.recv(4096)
            if not chunk:
                c.close()
                return
            d += chunk
            if len(d) > 65536:
                break
        log("REQ: " + repr(d[:150]))
        line = d.split(b'\r\n')[0].decode('utf-8', errors='replace')
        parts = line.split()
        log("PARTS: " + repr(parts))

        if len(parts) >= 2 and parts[0].upper() == 'CONNECT':
            host_port = parts[1]
            host, port = host_port.rsplit(':', 1)
            port = int(port)
            log("CONNECT " + host + ":" + str(port))
            try:
                r = socket.create_connection((host, port), timeout=15)
                c.sendall(b'HTTP/1.1 200 Connection established\r\n\r\n')
                c.settimeout(None)
                relay(c, r)
                r.close()
            except Exception as e:
                log("CONNECT ERR: " + str(e))
                c.sendall(b'HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
        elif len(parts) >= 2:
            url = parts[1]
            if url.startswith('http://'):
                host = url.split('/')[2]
                path = url[len('http://' + host):]
                if not path:
                    path = '/'
            elif url.startswith('https://'):
                host = url.replace('https://', '').split('/')[0]
                path = '/' + url.replace('https://', '').split('/', 1)[1] if '/' in url.replace('https://', '') else '/'
            else:
                host = parts[1].split('/')[0] if '/' in parts[1] else parts[1]
                path = '/' + parts[1].split('/', 1)[1] if '/' in parts[1] else '/'
            log("HTTP " + parts[0] + " " + host + " " + path)
            try:
                r = socket.create_connection((host, 80), timeout=15)
                new_req = parts[0].encode() + b' ' + path.encode() + b' ' + parts[2].encode() + b'\r\n'
                for h in d.split(b'\r\n')[1:]:
                    if h.lower().startswith(b'host:'):
                        new_req += b'Host: ' + host.encode() + b'\r\n'
                    elif h.lower().startswith(b'proxy-connection:'):
                        pass
                    elif h.lower().startswith(b'accept-encoding:'):
                        new_req += b'Accept-Encoding: identity\r\n'
                    else:
                        new_req += h + b'\r\n'
                new_req += b'\r\n'
                r.sendall(new_req)
                relay(c, r)
                r.close()
            except Exception as e:
                log("HTTP ERR: " + str(e))
                c.sendall(b'HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
        else:
            c.sendall(b'HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
    except Exception as e:
        log("ERR: " + repr(e))
    finally:
        try:
            c.close()
        except:
            pass

if __name__ == '__main__':
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(('0.0.0.0', 8888))
    srv.listen(5)
    log("PROXY READY on port 8888")
    while True:
        try:
            c, _ = srv.accept()
            t = threading.Thread(target=handle, args=(c,), daemon=True)
            t.start()
        except Exception as e:
            log("ACCEPT ERR: " + repr(e))
