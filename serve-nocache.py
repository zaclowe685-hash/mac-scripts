#!/usr/bin/env python3
# Shared dev server for Zac's static web games/apps.
# Sends no-cache headers so every browser reload pulls fresh JS modules —
# the default `python3 -m http.server` caches ES modules hard, which made
# fixed code look broken (SPECIMEN, forest-walk, etc.).
#
# Usage: python3 ~/scripts/serve-nocache.py <folder> <port>
import http.server, socketserver, sys, functools, os

if len(sys.argv) != 3:
    sys.exit("usage: serve-nocache.py <folder> <port>")

DIRECTORY = os.path.expanduser(sys.argv[1])
PORT = int(sys.argv[2])


class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        super().end_headers()

    # Pretty routes, GitHub Pages style: a path that is not a file or folder
    # serves the project's own `404.html` (if it has one) instead of the bare
    # python error page, so e.g. Thornbridge can turn /meet/edward into
    # /?meet=edward itself. Projects without a 404.html behave exactly as before.
    def send_error(self, code, message=None, explain=None):
        page = os.path.join(DIRECTORY, '404.html')
        if code == 404 and os.path.isfile(page):
            body = open(page, 'rb').read()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            if self.command != 'HEAD':
                self.wfile.write(body)
            return
        super().send_error(code, message, explain)


NoCacheHandler.extensions_map.update({
    '.js': 'text/javascript',
    '.mjs': 'text/javascript',
    '.glb': 'model/gltf-binary',
    '.gltf': 'model/gltf+json',
    '.hdr': 'application/octet-stream',
})

handler = functools.partial(NoCacheHandler, directory=DIRECTORY)
socketserver.TCPServer.allow_reuse_address = True
with socketserver.TCPServer(("", PORT), handler) as httpd:
    print(f"Serving {DIRECTORY} at http://localhost:{PORT} (caching disabled)")
    httpd.serve_forever()
