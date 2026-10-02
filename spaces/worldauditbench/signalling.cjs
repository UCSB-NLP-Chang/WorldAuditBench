const http = require('node:http');
const {SignallingServer,InitLogging} = require('@epicgames-ps/lib-pixelstreamingsignalling-ue5.6');
InitLogging({logDir:'/tmp/worldauditbench-signal-logs',logLevelConsole:'warn',logLevelFile:'warn',logMessagesToConsole:'none'});
const server = http.createServer((req,res) => {
  res.writeHead(200, {'Content-Type':'application/json'});
  res.end(JSON.stringify({ready: signalling.streamerRegistry.count() > 0}));
});
const signalling = new SignallingServer({
  httpServer: server, streamerPort: 8888,
  streamerWsOptions: {host:'127.0.0.1'},
  peerOptions: process.env.WAB_TRANSPORT === 'webrtc'
    ? JSON.parse(process.env.WAB_ICE_CONFIG || '{"iceServers":[]}') : {iceServers:[]},
  maxSubscribers: 1, playerKeepaliveTimeout: 30000
});
server.listen(8889, '127.0.0.1');
