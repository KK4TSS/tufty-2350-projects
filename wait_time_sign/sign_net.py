# SPDX-License-Identifier: GPL-3.0-only
import json
import socket
import ssl
import time
import os
import struct
HTTP_MAX_BYTES = 65536

def ticks():
    return time.ticks_ms() if hasattr(time, 'ticks_ms') else int(time.monotonic() * 1000)


def difference(now, start):
    return time.ticks_diff(now, start) if hasattr(time, 'ticks_diff') else now - start


def ipv4(value):
    parts = value.split('.')
    return len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts)


def name_at(packet, position):
    labels, end, seen = [], None, set()
    while True:
        if position in seen or position >= len(packet):
            raise OSError('Invalid DNS name')
        seen.add(position)
        size = packet[position]
        if size & 192 == 192:
            if position + 1 >= len(packet):
                raise OSError('Truncated DNS name')
            if end is None:
                end = position + 2
            position = ((size & 63) << 8) | packet[position + 1]
            continue
        if size > 63 or position + 1 + size > len(packet):
            raise OSError('Invalid DNS label')
        position += 1
        if not size:
            return b'.'.join(labels).decode().lower(), end or position
        labels.append(packet[position:position + size])
        position += size


def answer(packet, query, host):
    if len(packet) < 12:
        raise OSError('Truncated DNS response')
    ident, flags, questions, count, _, _ = struct.unpack('!6H', packet[:12])
    if packet[:2] != query[:2] or flags & 0xFA0F != 0x8000 or questions != 1:
        raise OSError('DNS lookup failed')
    question, pos = name_at(packet, 12)
    if question != host.lower() or packet[pos:pos+4] != b'\x00\x01\x00\x01':
        raise OSError('DNS question mismatch')
    pos += 4
    records = []
    for _ in range(count):
        owner, pos = name_at(packet, pos)
        if pos + 10 > len(packet):
            raise OSError('Truncated DNS record')
        kind, cls, ttl, size = struct.unpack('!HHIH', packet[pos:pos+10])
        pos += 10
        if pos + size > len(packet):
            raise OSError('Truncated DNS data')
        if cls == 1 and kind == 1 and size == 4:
            records.append((owner, kind, '.'.join(str(n) for n in packet[pos:pos+4])))
        elif cls == 1 and kind == 5:
            alias, end = name_at(packet, pos)
            if end != pos + size:
                raise OSError('Invalid DNS alias')
            records.append((owner, kind, alias))
        pos += size
    target = host.lower()
    for _ in range(len(records) + 1):
        matches = [r for r in records if r[0] == target]
        for owner, kind, value in matches:
            if kind == 1:
                return value
        aliases = [r[2] for r in matches if r[1] == 5]
        if not aliases:
            break
        target = aliases[0]
    raise OSError('DNS address unavailable')


def resolve_ipv4(host, server=None, timeout=8):
    start = ticks()
    if timeout <= 0:
        raise OSError('DNS timeout')
    if ipv4(host):
        return host
    if server is None:
        import network
        server = network.WLAN(network.STA_IF).ifconfig()[3]
    if not ipv4(server) or server == '0.0.0.0':
        raise OSError('DNS server unavailable')
    query = bytearray(os.urandom(2) + b'\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00')
    for label in host.split('.'):
        encoded = label.encode()
        if not 1 <= len(encoded) <= 63:
            raise ValueError('Invalid DNS hostname')
        query.append(len(encoded))
        query.extend(encoded)
    query.extend(b'\x00\x00\x01\x00\x01')
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        remaining = timeout - difference(ticks(), start) / 1000
        if remaining <= 0:
            raise OSError('DNS timeout')
        sock.settimeout(remaining)
        # Numeric server address avoids the firmware's blocking hostname resolver.
        sock.sendto(query, (server, 53))
        while True:
            remaining = timeout - difference(ticks(), start) / 1000
            if remaining <= 0:
                raise OSError('DNS timeout')
            sock.settimeout(remaining)
            packet, source = sock.recvfrom(512)
            if source[0] == server and source[1] == 53 and packet[:2] == query[:2]:
                result = answer(packet, query, host)
                if difference(ticks(), start) >= timeout * 1000:
                    raise OSError('DNS timeout')
                return result
    finally:
        sock.close()


def sync_clock(rtc):
    # Keep the firmware's ordinary NTP sync; bound its hostname lookup first.
    import ntptime
    original = ntptime.host
    try:
        ntptime.host = resolve_ipv4(original, timeout=8)
        rtc.time_from_ntp()
    finally:
        ntptime.host = original

# Errors

class Cancelled(OSError):
    pass


class TLSFailure(OSError):
    pass


# Encrypted HTTP, without certificate verification (user-selected mode).

def milliseconds():
    if hasattr(time, 'ticks_ms'):
        return time.ticks_ms()
    return int(time.monotonic() * 1000)


def elapsed(now, then):
    if hasattr(time, 'ticks_diff'):
        return time.ticks_diff(now, then)
    return now - then


def tls_context():
    try:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        if hasattr(context, 'check_hostname'):
            context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return context
    except (OSError, ValueError, AttributeError, TypeError) as error:
        raise TLSFailure('TLS unavailable') from error


class Reader:
    def __init__(self, stream, budget):
        self.stream = stream
        self.budget = budget

    def read(self, amount):
        self.budget()
        chunk = self.stream.read(amount)
        self.budget()
        return chunk or b''

    def exact(self, amount):
        result = bytearray()
        while len(result) < amount:
            chunk = self.read(min(1024, amount - len(result)))
            if not chunk:
                raise OSError('Truncated response')
            result.extend(chunk)
        return result

    def line(self):
        result = bytearray()
        while len(result) <= 1024:
            char = self.read(1)
            if not char:
                raise OSError('Truncated HTTP headers')
            result.extend(char)
            if char == b'\n':
                return bytes(result)
        raise OSError('HTTP line too long')


def _response_text(reader, maximum):
    status = (yield from reader.line()).split()
    if len(status) < 2 or status[0] not in (b'HTTP/1.0', b'HTTP/1.1') or status[1] != b'200':
        raise OSError('HTTP response not OK')  # Redirects are deliberately not followed.
    headers = {}
    total = 0
    while True:
        line = (yield from reader.line())
        total += len(line)
        if total > 8192:
            raise OSError('HTTP headers too large')
        if line == b'\r\n':
            break
        if b':' not in line:
            raise OSError('Malformed HTTP header')
        key, value = line.split(b':', 1)
        key, value = key.strip().lower(), value.strip().lower()
        # CDN metadata may repeat; message framing must remain unambiguous.
        if key in headers and key in (b'content-length', b'transfer-encoding', b'content-encoding'):
            raise OSError('Duplicate HTTP framing header')
        headers[key] = value
    if headers.get(b'content-encoding', b'identity') != b'identity':
        raise OSError('Unsupported response encoding')
    transfer = headers.get(b'transfer-encoding')
    length = headers.get(b'content-length')
    body = bytearray()
    if transfer:
        if transfer != b'chunked' or length is not None:
            raise OSError('Unsupported HTTP framing')
        while True:
            size = int((yield from reader.line()).split(b';', 1)[0].strip(), 16)
            if size < 0 or size > maximum - len(body):
                raise OSError('Response too large')
            if size == 0:
                trailer_size = 0
                while True:
                    line = (yield from reader.line())
                    trailer_size += len(line)
                    if trailer_size > 8192:
                        raise OSError('HTTP trailers too large')
                    if line == b'\r\n':
                        break
                break
            body.extend((yield from reader.exact(size)))
            if (yield from reader.exact(2)) != b'\r\n':
                raise OSError('Malformed HTTP chunk')
    elif length is not None:
        size = int(length)
        if size < 0 or size > maximum:
            raise OSError('Response too large')
        body = (yield from reader.exact(size))
    else:
        while True:
            chunk = (yield from reader.read(min(1024, maximum - len(body) + 1)))
            if not chunk:
                break
            body.extend(chunk)
            if len(body) > maximum:
                raise OSError('Response too large')
    return body.decode('utf-8')


class _SyncReader:
    def __init__(self, reader):
        self.reader = reader

    def line(self):
        if False:
            yield
        return self.reader.line()

    def read(self, amount):
        if False:
            yield
        return self.reader.read(amount)

    def exact(self, amount):
        if False:
            yield
        return self.reader.exact(amount)


def response_text(reader, maximum):
    parser = _response_text(_SyncReader(reader), maximum)
    try:
        next(parser)
    except StopIteration as result:
        return result.value
    raise RuntimeError('Synchronous parser yielded')


def response_json(reader, maximum):
    return json.loads(response_text(reader, maximum))


def http_get_json(url, timeout=8, cancel=None):
    return json.loads(http_get_text(url, timeout, cancel))


def http_get_text(url, timeout=8, cancel=None):
    # Never allow a settings change or redirect to silently remove TLS.
    if not url.startswith('https://'):
        raise TLSFailure('HTTPS required')
    host, separator, path = url[8:].partition('/')
    if (not host or len(host) > 253 or
            any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-' for c in host)
            or any(ord(c) <= 32 or ord(c) >= 127 for c in path)):
        raise ValueError('Invalid HTTPS URL')
    context = tls_context()
    address = (socket.AF_INET, socket.SOCK_STREAM, 0, '', (resolve_ipv4(host), 443))
    raw = socket.socket(address[0], socket.SOCK_STREAM, address[2])
    stream = None
    started = milliseconds()

    def budget():
        if cancel is not None:
            cancel()
        remaining = timeout - elapsed(milliseconds(), started) / 1000
        if remaining <= 0:
            raise OSError('HTTP deadline exceeded')
        target = stream if stream is not None and hasattr(stream, 'settimeout') else raw
        target.settimeout(remaining)

    try:
        budget()
        raw.connect(address[-1])
        budget()
        try:
            # Keep SNI for virtual hosting; peer certificates are not verified.
            stream = context.wrap_socket(raw, server_hostname=host)
        except (OSError, ValueError) as error:
            raise TLSFailure('TLS handshake failed') from error
        request = ('GET /' + path + ' HTTP/1.0\r\nHost: ' + host +
                   '\r\nUser-Agent: TuftyWaitTime/1.0\r\nAccept: application/json\r\nAccept-Encoding: identity\r\nConnection: close\r\n\r\n').encode()
        offset = 0
        while offset < len(request):
            budget()
            written = stream.write(request[offset:])
            if not written:
                raise OSError('HTTP write failed')
            offset += written
        return response_text(Reader(stream, budget), HTTP_MAX_BYTES)
    finally:
        try:
            if stream is not None:
                stream.close()
        finally:
            raw.close()



# Cooperative transport: every network wait returns to the badge's UI loop.
# No worker threads, blocking hostname lookup or blocking TLS handshake.
import select


def _pending(error):
    for name in ('SSLWantReadError', 'SSLWantWriteError'):
        kind = getattr(ssl, name, None)
        if kind is not None and isinstance(error, kind):
            return True
    return bool(error.args) and error.args[0] in (4, 11, 35, 36, 114, 115, 119)


def _deadline(start, timeout):
    if difference(ticks(), start) >= timeout * 1000:
        raise OSError('Network timeout')


def _receive(stream, amount, start, timeout):
    while True:
        _deadline(start, timeout)
        try:
            result = stream.read(amount)
        except OSError as error:
            if not _pending(error):
                raise
            result = None
        if result is not None:
            # Bound work even when a whole response is already buffered in TLS.
            yield
            return result
        yield


def _resolve(host, server, timeout=8):
    if ipv4(host):
        return host
    if not ipv4(server) or server == '0.0.0.0':
        raise OSError('DNS server unavailable')
    start = ticks()
    query = bytearray(os.urandom(2) + b'\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00')
    for label in host.split('.'):
        encoded = label.encode()
        if not 1 <= len(encoded) <= 63:
            raise ValueError('Invalid DNS hostname')
        query.append(len(encoded))
        query.extend(encoded)
    query.extend(b'\x00\x00\x01\x00\x01')
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setblocking(False)
        while True:
            _deadline(start, timeout)
            try:
                sent = sock.sendto(query, (server, 53))
            except OSError as error:
                if not _pending(error):
                    raise
                sent = None
            yield
            if sent:
                break
        while True:
            _deadline(start, timeout)
            try:
                packet, source = sock.recvfrom(512)
            except OSError as error:
                if not _pending(error):
                    raise
                yield
                continue
            yield
            if source == (server, 53) and packet[:2] == query[:2]:
                return answer(packet, query, host)
    finally:
        sock.close()


class _AsyncReader:
    def __init__(self, stream, start, timeout):
        self.stream, self.start, self.timeout = stream, start, timeout
        self.buffer = b''

    def read(self, amount):
        _deadline(self.start, self.timeout)
        if self.buffer:
            result, self.buffer = self.buffer[:amount], self.buffer[amount:]
            return result
        return (yield from _receive(self.stream, min(1024, amount), self.start, self.timeout))

    def exact(self, amount):
        result = bytearray()
        while len(result) < amount:
            chunk = yield from self.read(min(1024, amount-len(result)))
            if not chunk:
                raise OSError('Truncated response')
            result.extend(chunk)
        return result

    def line(self):
        while True:
            _deadline(self.start, self.timeout)
            end = self.buffer.find(b'\n')
            if end >= 0:
                if end > 1024:
                    raise OSError('HTTP line too long')
                result, self.buffer = self.buffer[:end+1], self.buffer[end+1:]
                return result
            if len(self.buffer) > 1024:
                raise OSError('HTTP line too long')
            chunk = yield from _receive(self.stream, 1024, self.start, self.timeout)
            if not chunk:
                raise OSError('Truncated HTTP headers')
            self.buffer += chunk


class Refresh:
    """One park request, stepped by the UI; results become visible atomically."""
    def __init__(self, park_id, ssid, password, rtc):
        self.park_id = park_id
        self.ssid, self.password, self.rtc = ssid, password, rtc
        self.done, self.rides, self.checked, self.error = False, None, None, None
        self._wlan = None
        self._raw = self._stream = None
        self._task = self._run()

    def step(self):
        if self.done:
            return
        try:
            next(self._task)
        except StopIteration:
            self.done = True
        except (OSError, ValueError, MemoryError, TypeError, AttributeError) as error:
            self.error = ('Configure device Wi-Fi' if str(error) == 'Missing Wi-Fi'
                          else 'TLS connection failed' if isinstance(error, TLSFailure)
                          else 'Update failed / Hold B: Retry')
            self.close()

    def close(self):
        self.done = True
        try:
            self._task.close()
        except ValueError:
            # HOME may interrupt step() through Badgeware's pin callback.
            # The launcher resets immediately after on_exit; never block it.
            pass
        finally:
            for stream in (self._stream, self._raw):
                if stream is not None:
                    try:
                        stream.close()
                    except OSError:
                        pass
            self._raw = self._stream = None
            if self._wlan is not None:
                try:
                    self._wlan.active(False)
                except OSError:
                    pass

    def _clock(self, server):
        # Reuse a valid battery-backed RTC. First-time sync also yields on waits.
        if time.gmtime()[0] >= 2025:
            return
        address = yield from _resolve('pool.ntp.org', server, timeout=3)
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setblocking(False)
            start = ticks()
            query = bytearray(48)
            query[0] = 0x23
            query[40:48] = os.urandom(8)
            while True:
                _deadline(start, 3)
                try:
                    sent = sock.sendto(query, (address, 123))
                except OSError as error:
                    if not _pending(error):
                        raise
                    sent = None
                yield
                if sent:
                    break
            while True:
                _deadline(start, 3)
                try:
                    packet, source = sock.recvfrom(512)
                except OSError as error:
                    if not _pending(error):
                        raise
                    yield
                    continue
                yield
                if (source != (address, 123) or len(packet) < 48
                        or packet[24:32] != query[40:48]):
                    continue
                if packet[0] & 7 != 4 or packet[0] >> 6 == 3 or not 1 <= packet[1] <= 15:
                    raise OSError('Invalid clock response')
                seconds = struct.unpack('!I', packet[40:44])[0]
                delta = 2208988800 if time.gmtime(0)[0] == 1970 else 3155673600
                dt = time.gmtime(seconds-delta)
                if dt[0] < 2025:
                    raise OSError('Invalid clock time')
                import machine
                machine.RTC().datetime((dt[0], dt[1], dt[2], dt[6], dt[3], dt[4], dt[5], 0))
                self.rtc.localtime_to_rtc()
                return
        finally:
            sock.close()

    def _https(self, server):
        host = 'queue-times.com'
        address = yield from _resolve(host, server)
        start = ticks()
        raw = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._raw = raw
        stream = None
        poller = None
        try:
            raw.setblocking(False)
            try:
                raw.connect((address, 443))
            except OSError as error:
                if not _pending(error):
                    raise
            yield
            poller = select.poll()
            poller.register(raw, select.POLLOUT)
            while True:
                _deadline(start, 20)
                events = poller.poll(0)
                if events:
                    errors = select.POLLERR | select.POLLHUP
                    if events[0][1] & errors:
                        raise OSError('TCP connection failed')
                    break
                yield
            poller.unregister(raw)
            # Handshake is performed incrementally by subsequent read/write calls.
            context = tls_context()
            stream = context.wrap_socket(raw, server_hostname=host,
                                         do_handshake_on_connect=False)
            self._stream = stream
            stream.setblocking(False)
            yield
            request = ('GET /parks/%s/queue_times.json HTTP/1.0\r\nHost: %s\r\n'
                       'User-Agent: TuftyWaitTime/1.1\r\nAccept: application/json\r\n'
                       'Accept-Encoding: identity\r\nConnection: close\r\n\r\n'
                       % (self.park_id, host)).encode()
            while request:
                _deadline(start, 20)
                # Keep this exact pending bytes object across TLS WANT_* retries.
                try:
                    sent = stream.write(request)
                except OSError as error:
                    if not _pending(error):
                        raise
                    sent = None
                if sent == 0:
                    raise OSError('HTTP write failed')
                if sent is not None:
                    request = request[sent:]
                yield
            reader = _AsyncReader(stream, start, 20)
            return (yield from _response_text(reader, HTTP_MAX_BYTES))
        finally:
            if poller is not None:
                try:
                    poller.unregister(raw)
                except (OSError, KeyError):
                    pass
            try:
                if stream is not None:
                    stream.close()
            finally:
                raw.close()
                self._raw = self._stream = None

    def _run(self):
        import network
        import sign_core
        try:
            if not self.ssid:
                raise ValueError('Missing Wi-Fi')
            self._wlan = network.WLAN(network.STA_IF)
            self._wlan.active(True)
            if not self._wlan.isconnected():
                self._wlan.connect(self.ssid, self.password)
            start = ticks()
            yield
            while not self._wlan.isconnected():
                _deadline(start, 15)
                if self._wlan.status() < 0:
                    raise OSError('Wi-Fi failed')
                yield
            server = self._wlan.ifconfig()[3]
            try:
                yield from self._clock(server)
            except (OSError, ValueError):
                pass  # Clock failure must not hide otherwise usable park readings.
            payload = yield from self._https(server)
            # Parsing a bounded response and publishing happen only on the UI core.
            self.rides = sign_core.parse(json.loads(payload))
            self.checked = sign_core.stamp()
        finally:
            if self._wlan is not None:
                self._wlan.active(False)
