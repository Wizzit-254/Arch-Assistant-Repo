import socket, threading, select, sys, urllib.request, ssl, os

def log(msg):
    try:
        sys.stderr.write(str(msg) + "\n")
        sys.stderr.flush()
    except:
        pass

log("STARTING PROXY v20")

def handle(c, addr):
    try:
        log("CONNECTION from " + str(addr))
        c.settimeout(10)
        d = b''
        while b'\r\n\r\n' not in d:
            try:
                chunk = c.recv(4096)
                if not chunk:
                    log("CLIENT CLOSED")
                    return
                d += chunk
                if len(d) > 65536:
                    break
            except socket.timeout:
                log("Timeout reading headers: " + repr(d[:200]))
                return
        log("RECEIVED: " + repr(d[:200]))
        try:
            fl = d.split(b'\r\n')[0].decode('utf-8', errors='replace')
        except:
            fl = ''
        parts = fl.split()
        log("PARTS: " + repr(parts))

        if len(parts) >= 2 and parts[0].upper() == 'CONNECT':
            host_port = parts[1]
            try:
                host, port = host_port.rsplit(':', 1)
                port = int(port)
            except Exception as e:
                log("CONNECT parse error: " + str(e))
                c.sendall(b'HTTP/1.1 400 Bad Request\r\nConnection: close\r\n\r\n')
                return
            try:
                log("CONNECTING to " + host + ":" + str(port))
                r = socket.create_connection((host, port), timeout=15)
                c.sendall(b'HTTP/1.1 200 Connection established\r\n\r\n')
                c.settimeout(None)
                socks = [c, r]
                while True:
                    try:
                        rd, _, _ = select.select(socks, [], [], 60)
                    except:
                        break
                    for s in rd:
                        try:
                            chunk = s.recv(4096)
                            if not chunk:
                                return
                            if s is c:
                                r.sendall(chunk)
                            else:
                                c.sendall(chunk)
                        except:
                            return
            except Exception as e:
                log("CONNECT ERR: " + str(e))
                c.sendall(b'HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
        elif len(parts) >= 2 and parts[0].upper() in ('GET', 'POST', 'PUT', 'DELETE', 'HEAD', 'OPTIONS', 'PATCH'):
            url = parts[1]
            log("URL: " + url)
            if url.startswith('http://'):
                host = url.split('/')[2]
            elif url.startswith('https://'):
                host = url.replace('https://', '').split('/')[0]
            else:
                host = '127.0.0.1'
            log("HOST: " + host)
            try:
                log("HTTP CONNECTING to " + host + ":80")
                remote = socket.create_connection((host, 80), timeout=15)
                remote.sendall(d)
                socks = [c, remote]
                while True:
                    try:
                        rd, _, _ = select.select(socks, [], [], 60)
                    except:
                        break
                    for s in rd:
                        try:
                            chunk = s.recv(4096)
                            if not chunk:
                                return
                            if s is c:
                                remote.sendall(chunk)
                            else:
                                c.sendall(chunk)
                        except:
                            return
            except Exception as e:
                log("GET ERR: " + str(e))
                c.sendall(b'HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
        else:
            log("UNKNOWN request: " + fl)
            c.sendall(b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK')
    except Exception as e:
        log("HANDLE ERR: " + repr(e))
    finally:
        try:
            c.close()
        except:
            pass

if __name__ == '__main__':
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(('127.0.0.1', 8888))
    srv.listen(5)
    log("PROXY READY on 127.0.0.1:8888")
    while True:
        try:
            c, addr = srv.accept()
            t = threading.Thread(target=handle, args=(c, addr))
            t.daemon = True
            t.start()
        except Exception as e:
            log("ACCEPT ERR: " + repr(e))
