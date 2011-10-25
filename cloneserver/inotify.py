#!/usr/bin/env python

import pyinotify
import os

class Watch(pyinotify.ProcessEvent):
	def __init__(self):
		self.__mask = pyinotify.IN_DELETE | pyinotify.IN_CREATE | \
		  pyinotify.IN_CLOSE_WRITE | pyinotify.IN_ATTRIB | \
		  pyinotify.IN_MOVED_FROM | pyinotify.IN_MOVED_TO
		self.__wdd = {}
		self.__wm = pyinotify.WatchManager()
		self.__notifier = pyinotify.Notifier(self.__wm, self)

	def watch_folder(self, name):
		self.__wdd.update(self.__wm.add_watch(name, self.__mask, rec=True))
		print "Watching", len(self.__wdd), "folders"

	def unwatch_folder(self, name):
		if name in self.__wdd:
			self.__wm.rm_watch(self.__wdd[name])
			del self.__wdd[name]
		print "Watching", len(self.__wdd), "folders"

	def loop(self):
		self.__notifier.loop()

	def stop(self):
		self.__wm.rm_watch(self.__wdd.values())
		self.__notifier.stop()

	def process_IN_CREATE(self, event):
		if event.dir:
			self.watch_folder(event.pathname)
			self.on_event('create-dir', event.pathname)
		elif os.stat(event.pathname).st_nlink > 1:
			self.on_event('link', event.pathname)
		elif os.path.islink(event.pathname):
			self.on_event('softlink', event.pathname)

	def process_IN_DELETE(self, event):
		if event.dir:
			self.unwatch_folder(event.pathname)
			self.on_event('delete-dir', event.pathname)
		else:
			self.on_event('delete', event.pathname)

	def process_IN_CLOSE_WRITE(self, event):
		self.on_event('write', event.pathname)

	def process_IN_MOVED_TO(self, event):
		self.on_event('move', event.src_pathname, event.pathname)

	def process_IN_ATTRIB(self, event):
		self.on_event('attrib', event.pathname)

	def on_event(self, type, path):
		print type, path

if __name__=='__main__':
	import sys
	watcher = Watch()
	watcher.watch_folder(sys.argv[1])
	watcher.loop()
