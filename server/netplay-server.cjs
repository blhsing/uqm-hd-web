'use strict';
/* eslint-disable @typescript-eslint/no-require-imports */

const http = require('node:http');
const { WebSocket, WebSocketServer } = require('ws');

const rooms = new Map();
const maximumRooms = 2048;
const maximumQueuedBytes = 2 * 1024 * 1024;
const maximumQueuedFrames = 512;
const roomLifetimeMs = 30 * 60 * 1000;

function json(response, status, body) {
  response.writeHead(status, {
    'Content-Type': 'application/json; charset=utf-8',
    'Cache-Control': 'no-store',
    'X-Content-Type-Options': 'nosniff',
  });
  response.end(JSON.stringify(body));
}

function parseRoom(request) {
  const url = new URL(request.url, 'http://localhost');
  const room = url.searchParams.get('room') || '';
  const match = /^(\d{1,3}(?:\.\d{1,3}){3}):(\d{1,5})$/.exec(room);
  if (!match) return null;
  const octets = match[1].split('.').map(Number);
  const port = Number(match[2]);
  if (octets.some(value => value > 255) || port < 1024 || port > 65535) return null;
  return `${match[1]}:${port}`;
}

function originAllowed(request) {
  const origin = request.headers.origin;
  if (!origin) return false;
  try {
    const hostname = new URL(origin).hostname.toLowerCase();
    const appHostname = String(process.env.WEBSITE_HOSTNAME || '').toLowerCase();
    return hostname === appHostname || hostname === 'localhost' || hostname === '127.0.0.1';
  } catch {
    return false;
  }
}

function closeEndpoint(endpoint, code, reason) {
  if (endpoint.socket.readyState === WebSocket.OPEN || endpoint.socket.readyState === WebSocket.CONNECTING) {
    endpoint.socket.close(code, reason);
  }
}

function disposeRoom(room, code = 1012, reason = 'Peer disconnected') {
  if (room.disposed) return;
  room.disposed = true;
  clearTimeout(room.timer);
  rooms.delete(room.key);
  for (const endpoint of room.endpoints) closeEndpoint(endpoint, code, reason);
}

function refreshRoomTimer(room) {
  clearTimeout(room.timer);
  room.timer = setTimeout(() => disposeRoom(room, 1001, 'Room expired'), roomLifetimeMs);
}

function deliver(endpoint, data, isBinary) {
  const peer = endpoint.peer;
  if (peer?.socket.readyState === WebSocket.OPEN) {
    peer.socket.send(data, { binary: isBinary });
    return;
  }

  const copy = Buffer.from(data);
  endpoint.queue.push({ data: copy, isBinary });
  endpoint.queuedBytes += copy.length;
  if (endpoint.queue.length > maximumQueuedFrames || endpoint.queuedBytes > maximumQueuedBytes) {
    disposeRoom(endpoint.room, 1009, 'Handshake queue limit exceeded');
  }
}

function flush(endpoint) {
  if (endpoint.peer?.socket.readyState !== WebSocket.OPEN) return;
  for (const frame of endpoint.queue) endpoint.peer.socket.send(frame.data, { binary: frame.isBinary });
  endpoint.queue.length = 0;
  endpoint.queuedBytes = 0;
}

const server = http.createServer((request, response) => {
  const url = new URL(request.url, 'http://localhost');
  if (url.searchParams.get('status') === '1') {
    json(response, 200, { ok: true, waitingRooms: [...rooms.values()].filter(room => room.endpoints.length === 1).length });
  } else {
    json(response, 426, { error: 'This endpoint accepts WebSocket connections for network Super Melee.' });
  }
});

const websocketServer = new WebSocketServer({
  server,
  maxPayload: 1024 * 1024,
  perMessageDeflate: false,
});

websocketServer.on('connection', (socket, request) => {
  if (!originAllowed(request)) {
    socket.close(1008, 'Origin is not allowed');
    return;
  }

  const key = parseRoom(request);
  if (!key) {
    socket.close(1008, 'Invalid room address or port');
    return;
  }

  let room = rooms.get(key);
  if (!room) {
    if (rooms.size >= maximumRooms) {
      socket.close(1013, 'Relay is at capacity');
      return;
    }
    room = { key, endpoints: [], disposed: false, timer: null };
    rooms.set(key, room);
  } else if (room.endpoints.length >= 2) {
    socket.close(1013, 'Room already has two players');
    return;
  }

  const endpoint = { socket, room, peer: null, queue: [], queuedBytes: 0, alive: true };
  room.endpoints.push(endpoint);
  refreshRoomTimer(room);

  if (room.endpoints.length === 2) {
    const [first, second] = room.endpoints;
    first.peer = second;
    second.peer = first;
    flush(first);
    flush(second);
  }

  socket.on('message', (data, isBinary) => {
    if (room.disposed) return;
    refreshRoomTimer(room);
    deliver(endpoint, data, isBinary);
  });
  socket.on('pong', () => { endpoint.alive = true; });
  socket.on('error', () => disposeRoom(room));
  socket.on('close', () => disposeRoom(room));
});

const heartbeat = setInterval(() => {
  for (const room of rooms.values()) {
    for (const endpoint of room.endpoints) {
      if (!endpoint.alive) {
        disposeRoom(room, 1001, 'Peer timed out');
        break;
      }
      endpoint.alive = false;
      if (endpoint.socket.readyState === WebSocket.OPEN) endpoint.socket.ping();
    }
  }
}, 30_000);
heartbeat.unref();

server.listen(process.env.PORT || 8080);
