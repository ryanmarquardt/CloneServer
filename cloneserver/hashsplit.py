#!/usr/bin/env python

from _hashsplit import *

def split(file, max_chunk_size=None):
	try:
		while True:
			yield read_chunk(file, max_chunk_size)
	except EOFError:
		return
