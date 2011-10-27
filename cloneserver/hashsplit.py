#!/usr/bin/env python

CHAR_OFFSET=31
WINDOWSIZE=128
DATASIZE=20480

class Chunk(object):
	def __init__(self, offset):
		self.offset = offset
		self.s1 = WINDOWSIZE * CHAR_OFFSET
		self.s2 = WINDOWSIZE * (WINDOWSIZE-1) * CHAR_OFFSET
		self.data = ''

	@property
	def length(self): return len(self.data)

	@property
	def digest(self): return self.s1 << 16 | self.s2

	def append(self, add, biggest):
		cursor = self.length - WINDOWSIZE
		drop = ord(self.data[cursor]) if cursor >= 0 else 0
		self.data += chr(add)
		self.s1 += add - drop
		self.s1 &= 0xffff
		self.s2 += self.s1 - WINDOWSIZE * (drop + CHAR_OFFSET)
		self.s2 &= 0xffff
		return not biggest or self.length < biggest

def read_chunk(file, smallest=0, biggest=None):
	chunk = Chunk(file.tell())
	smallest = max(WINDOWSIZE,smallest)
	last = False
	while (~chunk.digest) & 0x1fff or chunk.length < smallest:
		char = file.read(1)
		if not char:
			last = True
			break
		if not chunk.append(ord(char), biggest):
			break
	return chunk, last

def hashsplit(file, smallest=0, biggest=None):
	if isinstance(file, basestring):
		file = open(file,'rb')
	last = False
	while not last:
		chunk,last = read_chunk(file, smallest=smallest, biggest=biggest)
		yield chunk

import sys
for chunk in hashsplit(sys.argv[1], biggest=DATASIZE):
	print '%i:%s' % (chunk.length, chunk.data)
