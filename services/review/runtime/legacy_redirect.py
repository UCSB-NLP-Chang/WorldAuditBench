"""Keep the former Subway bookmark pointed at the shared review queue."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlsplit,parse_qs,urlencode
class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  if self.path=='/health':
   body=b'{"ok":true,"redirect":"https://review.150-230-45-149.sslip.io/"}';self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body);return
  case=parse_qs(urlsplit(self.path).query).get('case',[''])[0]
  location='https://review.150-230-45-149.sslip.io/'+('?' + urlencode({'case':case}) if case else '')
  self.send_response(302);self.send_header('Location',location);self.send_header('Content-Length','0');self.end_headers()
 def log_message(self,*args):pass
ThreadingHTTPServer(('127.0.0.1',8093),Handler).serve_forever()
