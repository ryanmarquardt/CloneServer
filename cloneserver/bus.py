#!/usr/bin/env python

import threading
import Queue

class Bus(threading.Thread):
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

