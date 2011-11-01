#!/usr/bin/env python
'''

'''

import socket
import hashlib
import hmac
import random
import os
import threading
import Queue
import time
import select

import inotify
from dal import DB, Table, Field
from bus import Bus

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
			for sock in select.select([self], [], [], 1)[0]:
				self.on_message(*sock.recvfrom(65535)) #Max 1 udp packet

	def stop(self):
		self.running = False

##For client with peerid deadbeef0001:
## Notify peers about an updated file
#deadbeef0001 Updated 25:Music/Beatles/Imagine.mp3\n
## Request information about the file
#deadbeef0001 Request 25:Music/Beatles/Imagine.mp3\n
## Request information about all files
#deadbeef0001 Request 0:\n

class Broadcaster(BGServer):
	def __init__(self, bus, peerid, address, name=None):
		self.bus = bus
		self.peerid = peerid
		BGServer.__init__(self, address, name=name or 'Broadcaster')

	def send(self, *message):
		message = ('%012x' % self.peerid,) + message
		print 'Sending:', ' '.join(message)
		self.announcer.sendto(' '.join(message), ('<broadcast>', self.port))

	def on_message(self, data, address):
		try:
			assert data[12] == ' ' and data[20] == ' ' and data[-1] == '\n'
			peerid = int(data[:12], 16)
			verb = data[13:20]
			arg = data[21:]
			s = arg.find(':',1,4)
			assert s != -1
			l = int(arg[:s])
			path = arg[s+1:l+s+1]
			self.bus.submit(MessageType.HeardFromPeer, address=address, peerid=peerid)
			if verb == 'Request':
				self.bus.submit(MessageType.Request, address=address, peerid=peerid, path=path)
			elif verb == 'Updated':
				self.bus.submit(MessageType.RemoteUpdate, address=address, peerid=peerid, path=path)
			else:
				raise Exception
		except:
			self.bus.submit(MessageType.BadData, address=address)

class Whisperer(BGServer):
	def __init__(self, bus, address, name=None):
		BGServer.__init__(self, address, name=name or 'Whisperer')

class Message(attrdict): pass

MessageType = attrdict(
	ANY = None,
	HeardFromPeer = 'heard-from-peer',
	Updated = 'updated',
	Request = 'request',
	BadData = 'bad-data',
	Start = 'start',
)

def iterqueue(queue, timeout=0):
	while True:
		try:
			yield queue.get(timeout=timeout)
		except Queue.Empty:
			break

class Peer(object):
	def __init__(self, share_path, host=None, port=None):
		self.host, self.port = (host or ALL), (port or PORT)
		self.db = dal.DB('sqlite://')
		self.db.define_table('config',
			dal.Field('key', key=True), dal.Field('value')
			)
		if 'peerid' not in self.db.config:
			self.db.config['peerid'] = hex(random.getrandbits(48))[2:14]
		self.db.define_table('peers',
			dal.Field('peerid'),
			dal.Field('address', serialize=lambda x:'%s:%i'%x,
			 convert=lambda x:tuple(f(a) for f,a in zip((str,int),x.rsplit(':',1)))),
			dal.Field('ignore', default=False),
			)
		self.db.define_table('resources',
			dal.Field('path', key=True),
			dal.Field('age', int),
			dal.Field('real_path'),
			)
		if os.path.isdir(share_path) and share_path[-1] != '/':
			share_path += '/'
		for path in find(os.path.abspath(share_path)):
			short_path = path[len(share_path):]
			print path, short_path
			self.db.resources.insert(path=short_path, age=mod_time(os.stat(path)), real_path=path)
		self.bus = Bus()
		self.bus.connect(MessageType.HeardFromPeer, self.introduce)
		self.bus.connect(MessageType.Request, self.notify)
		self.bus.connect(MessageType.RemoteUpdate, self.remote_update)
		self.public = Broadcaster(self.bus, self.db.config['peerid'], (self.host, self.port))
		self.private = Whisperer(self.bus, (self.host, self.port))

	def start(self):
		self.bus.start()
		self.public.start()
		self.private.start()

	def announce(self):
		self.broadcaster.send('Hello?')

	def remote_update(self, message):
		if self.filter(message.path):
			self.private.retrieve(message.address, message.path)

	def introduce(self, message):
		print message
		self.db.peers.insert(**message)

	def notify(self, message):
		print message
		self.public.send(self.db.resources[message.path].age)

	def stop(self):
		self.private.stop()
		self.public.stop()
		self.bus.stop()

if __name__=='__main__':
	p = Peer('/home/ryan/bin')
	try:
		p.start()
		while True:
			time.sleep(1)
	finally:
		p.stop()
