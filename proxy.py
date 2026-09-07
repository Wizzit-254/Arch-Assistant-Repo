import socket, sys

def log(msg):
    sys.stderr.write(str(msg) + "\n")
    sys.stderr.flush()

srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(('0.0.0.0', 8888))
srv.listen(5)
log("ECHO PROXY READY on port 8888")

while True:
    try:
        c, addr = srv.accept()
        log("CONN from " + str(addr))
        data = c.recv(4096)
        log("GOT: " + repr(data[:200]))
        c.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 13\r\n\r\nHello from echo")
        c.close()
    except Exception as e:
        log("ERR: " + repr(e))
