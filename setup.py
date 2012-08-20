#!/usr/bin/env python

from distutils.core import setup, Extension

setup(name="CloneServer", version="0.1",
	author="Ryan Marquardt",
	author_email="ryan.marquardt@gmail.com",
	description="Local network resource sharing",
	url="http://orbnauticus.github.org/cloneserver",
	license="Simplified BSD License",
	scripts=['bin/client', 'bin/server'],
	packages=['cloneserver', 'hashsplit'],
	ext_modules=[
		Extension("hashsplit/_hashsplit", ["hashsplit/hashsplitmodule.c"])
	],
)
