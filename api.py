"""Opt-in local HTTP server. Never expose without token and firewall restrictions."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def serve(controller, host, port, token):
    if not token or len(token) < 20:
        raise ValueError('Token da API precisa ter pelo menos 20 caracteres')

    class Handler(BaseHTTPRequestHandler):
        def _send(self, status, payload):
            body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)

        def _auth(self):
            import hmac
            expected = 'Bearer ' + token
            if not hmac.compare_digest(self.headers.get('Authorization', ''), expected):
                self._send(401, {'error': 'Não autorizado'})
                return False
            return True

        def do_GET(self):
            if not self._auth():
                return
            if self.path == '/api/monitors':
                try:
                    self._send(200, {'monitors': [m.to_dict() for m in controller.scan()]})
                except Exception as exc:
                    self._send(500, {'error': str(exc)})
            else:
                self._send(404, {'error': 'Endpoint desconhecido'})

        def do_POST(self):
            if not self._auth():
                return
            if self.path not in ('/api/switch', '/api/profile'):
                self._send(404, {'error': 'Endpoint desconhecido'})
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 4096:
                    self._send(400, {'error': 'Tamanho inválido'})
                    return
                body = json.loads(self.rfile.read(length))
                target = body.get('target')
                if target not in ('A', 'B'):
                    raise ValueError('target deve ser A ou B')
                if self.path == '/api/switch':
                    result = controller.switch_one(body['monitor_id'], target)
                else:
                    result = controller.switch_all(target)
                self._send(200, {'result': result})
            except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
                self._send(400, {'error': str(exc)})
            except Exception as exc:
                self._send(500, {'error': str(exc)})

    server = ThreadingHTTPServer((host, port), Handler)
    print(f'API iniciada em http://{host}:{port} (token obrigatório)')
    server.serve_forever()
