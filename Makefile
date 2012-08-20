
all: build

build:
	@python setup.py build

.PHONY: all build test clean

test: build
	@cd build/lib.linux-i686-2.7; PYTHONPATH=$(PWD) python hashsplit/__init__.py
	@PYTHONPATH=$(PWD) python cloneserver/__init__.py

clean:
	@rm -r build
	@rm -r dist
