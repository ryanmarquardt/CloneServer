#!/usr/bin/env python

CHAR_OFFSET=31
WINDOWSIZE=128

class Chunk(object):
	def __init__(self, offset):
		self.offset = offset
		self.length = 0
		self.s1 = WINDOWSIZE * CHAR_OFFSET
		self.s2 = WINDOWSIZE * (WINDOWSIZE-1) * CHAR_OFFSET
		self.digest = (self.s1 << 16 | self.s2)
		self.window = [0] * WINDOWSIZE
		self.window_offset = 0

	def append(self, add):
		drop = self.window[self.window_offset]
		self.window[self.window_offset] = add
		self.window_offset = (self.window_offset+1) % WINDOWSIZE
		self.s1 += add - drop
		self.s1 &= 0xffff
		self.s2 += self.s1 - WINDOWSIZE * (drop + CHAR_OFFSET)
		self.s2 &= 0xffff
		self.digest = (self.s1 << 16 | self.s2)
		self.length += 1

def read_chunk(file, smallest=0, biggest=None):
	chunk = Chunk(file.tell())
	smallest = max(WINDOWSIZE,smallest)
	last = False
	while (~chunk.digest) & 0x1fff or chunk.length < smallest:
		char = file.read(1)
		if not char:
			last = True
			break
		chunk.append(ord(char))
		if biggest and chunk.length >= biggest:
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
for chunk in hashsplit(sys.argv[1], biggest=0):
	print '%i\t%i\t%08x' % (chunk.offset, chunk.length, chunk.digest)
