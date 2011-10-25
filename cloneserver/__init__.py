#!/usr/bin/env python
'''

'''

import socket
import hashlib
import hmac
import random
import threading
import Queue
import time
import select

import inotify
import dal

PORT = 5979
ALL = ''

def find(path='.', dirs=False):
	for f in os.listdir(path):
		p = os.path.join(path, f)
		if os.path.isdir(p):
			if dirs: yield p
			for g in find(p): yield g
		else:
			yield p

class attrdict(dict): __getattr__,__setattr__,__delattr__ = dict.get,dict.__setitem__,dict.__delitem__

Ciphers = attrdict()
for algorithm in ('Blowfish', 'AES', 'DES3'):
	try:
		Ciphers[algorithm] = __import__('Crypto.Cipher.%s' % algorithm, globals=globals(), fromlist=[algorithm])
		Ciphers.setdefault('preferred', algorithm)
	except ImportError:
		pass

class Socket(object):
	def __init__(self, ip6=False, tcp=True):
		self._sock = socket.socket(socket.AF_INET6 if ip6 else socket.AF_INET, socket.SOCK_STREAM if tcp else socket.SOCK_DGRAM)

	def fileno(self): return self._sock.fileno()

	broadcast = property(lambda self:self._sock.getsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST),
		lambda self,val:self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, bool(val)))
	reuseaddr = property(lambda self:self._sock.getsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR),
		lambda self,val:self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, bool(val)))

	def connect(self, (host, port)): self._sock.connect((host, port))
	def bind(self, (host, port)): self._sock.bind((host, port))
	def listen(self, backlog): self._sock.listen(backlog)
	def accept(self): return self._sock.accept()
	def recvfrom(self, size): return self._sock.recvfrom(size)
	def recv(self, size): return self._sock.recv(size)
	def sendto(self, data, address): return self._sock.sendto(data, address)
	def send(self, data): return self._sock.send(data)

mod_time = lambda st:max(st.st_mtime, st.st_ctime)

class FileChanged(Exception): pass

class ShareWatcher(inotify.Watch):
	def __init__(self, bus, path):
		inotify.Watch.__init__(self)
		self.bus = bus
		inotify.Watch.watch_folder(path)

	def on_event(self, type, path, topath=None):
		self.bus.submit(MessageType.ResourceChanged, path=path, topath=topath)

class Share(object):
	def __init__(self, public_name, base_path, cipher=None, key=None):
		self.base_path = base_path
		self.most_recent = 0
		self.state = {}
		for path in find(self.base_path):
			last_change = mod_time(os.stat(path))
			self.state[path] = last_change
			self.most_recent = max(self.most_recent, last_change)

	def getstate(self, after=0):
		for path,timestamp in self.state.iteritems():
			if timestamp > after:
				yield (path, timestamp)

	def getresource(self, path, timestamp, block_size=1<<15):
		reader = open(path, 'rb')
		while mod_time(os.stat(path)) == timestamp:
			block = reader.read(block_size)
			pos = reader.tell()
			if block: yield block
			else: return
		#Fell through: the file was changed while we were reading it
		raise FileChanged

class BGServer(threading.Thread, Socket):
	def __init__(self, address, name='BGServer'):
		threading.Thread.__init__(self, name=name)
		Socket.__init__(self, tcp=False)
		self.reuseaddr = True
		self.bind(address)
		self.running = True

	def run(self):
		while self.running:
			for sock in select.select(self.sockets, [], [], 1)[0]:
				self.on_message(*sock.recvfrom(65535)) #Max 1 udp packet

	def stop(self):
		self.running = False

class Broadcaster(BGServer):
	_inst_count = 0
	def __init__(self, bus, peerid, address, name=None):
		self.bus = bus
		self.peerid = peerid
		self._inst_count += 1
		name = name or 'Broadcaster-%i' % self._inst_count
		BGServer.__init__(self, address, name=name)

	def send(self, *message):
		message = ('%012x' % self.peerid,) + message
		self.announcer.sendto(' '.join(message), ('<broadcast>', self.port))

	def on_message(self, data, address):
		try:
			peerid = int(data[:12], 16)
			assert data[13] == ' '
			self.bus.submit(MessageType.HeardFromPeer, address=(host, port), peerid=peerid)
			if data[14:] == 'Hello?\n':
				type = MessageType.PeerRequest
			elif data[14:] == 'Update\n':
				type = MessageType.Update
			else:
				raise Exception
		except:
			self.bus.submit(MessageType.BadData, address=(host, port))

class Whisperer(BGServer):
	_inst_count = 0
	def __init__(self, bus, *addresses, **kwargs):
		self._inst_count += 1
		kwargs.setdefault('name', 'Whisperer-%i' % self._inst_count)
		BGServer.__init__(self, *addresses, **kwargs)

	def on_connect

class Message(attrdict): pass

MessageType = attrdict(
	ANY = None,
	NewPeer = 'new-peer',
	ResourceChanged = 'resource-changed',
)

def iterqueue(queue, timeout=0):
	while True:
		try:
			yield queue.get(timeout=timeout)
		except Queue.Empty:
			break

class Bus(Thread):
	def __init__(self):
		threading.Thread.__init__(self, name='Message Bus')
		self.messages = Queue.Queue()
		self.connect_lock = threading.Lock()
		self.callbacks = {}
		self._highest_i = 0

	def run(self):
		try:
			for m in iterqueue(self.messages, timeout=1):
				if m is None:
					return
				with self.connect_lock:
					for i, (type, func, args, kwargs) in self.callbacks.items():
						if type in (None, m.type):
							try:
								func(m, *args, **kwargs)
							except BaseException:
								del self.callbacks[i]
		finally:
			self.stop()

	def submit(self, message_type, **kwargs):
		self.messages.put(Message(type=message_type, **kwargs))

	def stop(self):
		self.messages.put(None)

	def connect(self, message_type, callback, *args, **kwargs):
		with self.connect_lock:
			self.callbacks[self._highest_i] = (message_type, callback, args, kwargs)
			self._highest_i += 1

class Peer(object):
	def __init__(self, host=None, port=None):
		self.host, self.port = (host or ALL), (port or PORT)
		self.db = dal.DB('sqlite://')
		self.config = self.db.define_table('config',
			dal.Field('key', key=True), dal.Field('value'))
		if 'peerid' not in self.config:
			self.config['peerid'] = hex(random.getrandbits(48))[2:14]
		self.peers = self.db.define_table('peers',
			dal.Field('peerid'),
			dal.Field('address', serialize=lambda x:'%s:%i'%x,
			 convert=lambda x:tuple(f(a) for f,a in zip((str,int),x.rsplit(':',1))))
			dal.Field('ignore', default=False),
			)
		self.bus = Bus()
		self.bus.connect(MessageType.NewPeer, self.introduce)
		self.public = Broadcaster(self.bus, self.config['peerid'], (self.host, self.port))
		self.private = Whisperer(self.bus, (self.host, self.port))

	def start(self):
		self.bus.start()
		self.public.start()
		self.private.start()

	def announce(self):
		self.broadcaster.send('Hello?')

	def introduce(self, message):
		print message
		self.db.peers.insert(**message)

	def receive(self, message, peer, port):
		if message == 'Hello?':
			self.peers[peer] = True

	def stop(self):
		self.bus.stop()
		self.public.stop()
		self.private.stop()

if __name__=='__main__':
	p = Peer()
	try:
		p.start()
		while True:
			time.sleep(1)
	finally:
		p.stop()
