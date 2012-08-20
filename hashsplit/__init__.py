#!/usr/bin/env python

"""

>>> sample_path = '/bin/bash'
>>> c_chunks = list(split(open(sample_path, 'rb')))

#Reference implementation with poor performance
>>> def read_chunk(source, chunk):
...   WINDOWSIZE, CHAR_OFFSET, BIGGEST = 128, 31, 20480
...   offset = source.tell()
...   s1 = WINDOWSIZE*CHAR_OFFSET
...   s2 = (s1 * (WINDOWSIZE-1)) & 0xffff
...   data = ''
...   chunk_digest = lambda :(s1 << 16 | s2) & 0x1fff
...   while not chunk_digest() or len(data) < WINDOWSIZE:
...     buf = source.read(1)
...     if not buf:
...       return data
...     cursor = len(data) - WINDOWSIZE
...     drop = ord(data[cursor]) if cursor >= 0 else 0
...     data += buf
...     s1 += ord(buf) - drop
...     s2 += s1 - WINDOWSIZE * (drop + CHAR_OFFSET)
...     if len(data) >= BIGGEST:
...       return data
>>> py_chunks = list(split(open(sample_path, 'rb')))
>>> py_chunks == c_chunks
True
>>> max(map(len, py_chunks)) <= 20480
True
>>> import os
>>> sum(map(len, py_chunks)) == os.stat(sample_path).st_size
True

"""

from _hashsplit import *

def split(file, max_chunk_size=None):
	try:
		while True:
			yield read_chunk(file, max_chunk_size)
	except EOFError:
		return

if __name__=='__main__':
	import doctest
	doctest.testmod()
