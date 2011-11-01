#!usr/bin/env python

import sys
import os
import cloneserver.hashsplit

sample = open('sample','rb')
count = 0
size = 0
#sys.stdout.write('\x1b[s')
for chunk in cloneserver.hashsplit.split(sample):
	count += 1
	size += len(chunk)
	#sys.stdout.write('\x1b[K%i\t%i\x1b[u' % (count,size))
	#sys.stdout.flush()
print
print os.stat(sample.name).st_size
