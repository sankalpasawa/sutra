// The close-flush check of upstream PR #377 (anthropics/sandbox-runtime), run against a bundled srt's own proxy modules:
// an origin writes 1 MiB of made-up bytes and closes at once; a client drains it slowly (16 KiB every 2 ms) over a Unix
// domain socket, so relayed bytes are still queued when the origin's FIN arrives. Prints {"connect": [...], "socks": [...]}.
import { connect, createServer } from 'node:net';
import { once } from 'node:events';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

const [dist, sockDir, transfers = '6'] = process.argv.slice(2);
const { createHttpProxyServer } = await import(pathToFileURL(join(dist, 'sandbox', 'http-proxy.js')).href);
const { createSocksProxyServer } = await import(pathToFileURL(join(dist, 'sandbox', 'socks-proxy.js')).href);
const SIZE = 1024 * 1024, CHUNK = 16 * 1024, EVERY_MS = 2, N = Number(transfers);

const origin = createServer(s => { s.on('error', () => {}); s.end(Buffer.alloc(SIZE, 0x78)); });
origin.listen(0, '127.0.0.1');
await once(origin, 'listening');
const port = origin.address().port;

async function listenUnix(server, name) {
  const path = join(sockDir, name);
  server.listen(path);
  await once(server, 'listening');
  return path;
}

function drainPaced(sock, handshake) {
  return new Promise(resolve => {
    let inTunnel = false, total = 0;
    const timer = setInterval(() => {
      const chunk = sock.read(inTunnel ? CHUNK : undefined);
      if (chunk === null) return;
      if (!inTunnel) {
        const rest = handshake(chunk);
        if (rest === null) return;
        inTunnel = true;
        total += rest.length;
      } else total += chunk.length;
    }, EVERY_MS);
    sock.on('error', () => {});
    sock.on('close', () => {
      let c;
      while ((c = sock.read()) !== null) total += c.length;
      clearInterval(timer);
      resolve(total);
    });
  });
}

const out = { size: SIZE, connect: [], socks: [] };

const http = createHttpProxyServer({ filter: () => true });
const httpPath = await listenUnix(http, 'h.sock');
for (let i = 0; i < N; i++) {
  const sock = connect({ path: httpPath });
  await once(sock, 'connect');
  sock.pause();
  sock.write(`CONNECT 127.0.0.1:${port} HTTP/1.1\r\nHost: 127.0.0.1:${port}\r\n\r\n`);
  let head = Buffer.alloc(0);
  out.connect.push(await drainPaced(sock, chunk => {
    head = Buffer.concat([head, chunk]);
    const end = head.indexOf('\r\n\r\n');
    if (end === -1) return null;
    if (!head.subarray(0, end).toString().startsWith('HTTP/1.1 200')) throw new Error('CONNECT refused');
    return head.subarray(end + 4);
  }));
}
http.close();

const wrapper = createSocksProxyServer({ filter: () => true });
const front = createServer(s => wrapper.handleConnection(s));
const frontPath = await listenUnix(front, 's.sock');
for (let i = 0; i < N; i++) {
  const sock = connect({ path: frontPath });
  await once(sock, 'connect');
  sock.pause();
  sock.write(Buffer.from([0x05, 0x01, 0x00]));          // version 5, one method: no auth
  let buf = Buffer.alloc(0), stage = 'greeting';
  out.socks.push(await drainPaced(sock, chunk => {
    buf = Buffer.concat([buf, chunk]);
    if (stage === 'greeting') {
      if (buf.length < 2) return null;
      if (buf[0] !== 0x05 || buf[1] !== 0x00) throw new Error('SOCKS greeting refused');
      buf = buf.subarray(2);
      stage = 'connect';
      sock.write(Buffer.from([0x05, 0x01, 0x00, 0x01, 127, 0, 0, 1, port >> 8, port & 0xff]));
    }
    if (buf.length < 10) return null;
    if (buf[1] !== 0x00) throw new Error('SOCKS CONNECT refused');
    return buf.subarray(10);
  }));
}
await wrapper.close();
front.close();
origin.close();
console.log(JSON.stringify(out));
