#include <Python.h>

#define MIN_CHUNK_SIZE 128
#define DEFAULT_MAX_CHUNK_SIZE 20480
#define MATCHBITS 13
#define MATCHMASK ((1<<MATCHBITS)-1)
#define CHAR_OFFSET 31

#define Raise(e,s) PyErr_SetString(e, s); return NULL

typedef struct {
	unsigned long int offset;
	uint16_t s1, s2;
	unsigned int length;
	uint8_t data[];
} Chunk;

Chunk * chunk_new(int size) {
	return (Chunk *)malloc(sizeof(Chunk) + size*sizeof(uint8_t));
}
void    chunk_delete(Chunk *self) { return free(self); }
uint    chunk_digest(Chunk *self) { return (self->s1 << 16) | self->s2; }

void chunk_init(Chunk *self, int offset) {
	self->offset = offset;
	self->s1 = MIN_CHUNK_SIZE * CHAR_OFFSET;
	self->s2 = (uint16_t)(MIN_CHUNK_SIZE * (MIN_CHUNK_SIZE-1) * CHAR_OFFSET);
	self->length = 0;
}

int chunk_append(Chunk *self, unsigned char add, long MAX_CHUNK_SIZE) {
	int cursor = self->length - MIN_CHUNK_SIZE;
	//Don't bother zeroing memory...
	uint8_t drop = (cursor >= 0) ? self->data[cursor] : 0 ;
	self->data[self->length++] = add;
	self->s1 += add - drop;
	self->s2 += self->s1 - MIN_CHUNK_SIZE * (drop + CHAR_OFFSET);
	return (self->length < MAX_CHUNK_SIZE);
	//Returns true if we can add more to this chunk
}

unsigned read_chunk(FILE *source, Chunk *chunk, long MAX_CHUNK_SIZE) {
	int buf;
	chunk_init(chunk, ftell(source));
	while ((~(chunk_digest(chunk)) & MATCHMASK) || (chunk->length < MIN_CHUNK_SIZE)) {
		if ((buf = fgetc(source))==EOF)
			return (chunk->length > 0); //No more if this chunk has nothing
		if (!(chunk_append(chunk, (char)(buf & 0xff), MAX_CHUNK_SIZE)))
			return 1; //Chunk has data, but it's too big to take more
	}
	return 1;
}

static PyObject * hashsplit_read_chunk(PyObject *self, PyObject *args) {
	PyObject *source_file = NULL; //gcc complains if these aren't initialized
	PyObject *max_chunk_size = NULL;
	long MAX_CHUNK_SIZE;
	PyObject *result;
	Chunk *chunk;
	FILE *source;

	if (!PyArg_UnpackTuple(args, "read_chunk", 1, 2, &source_file, &max_chunk_size)) return NULL;
	if (!(source = PyFile_AsFile(source_file))) {
		Raise(PyExc_TypeError, "Expected file or file descriptor");
	}
	if (!max_chunk_size || max_chunk_size == Py_None) {
		MAX_CHUNK_SIZE = DEFAULT_MAX_CHUNK_SIZE;
	} else if ((MAX_CHUNK_SIZE = PyInt_AsLong(max_chunk_size))==-1 && PyErr_Occurred()) {
		Raise(PyExc_TypeError, "max_chunk_size should be an integer");
	}
	if (MAX_CHUNK_SIZE < MIN_CHUNK_SIZE) {
		Raise(PyExc_ValueError, "max_chunk_size must be larger than MIN_CHUNK_SIZE"); }
	if (!(chunk = chunk_new(MAX_CHUNK_SIZE))) return PyErr_NoMemory();
	if (!read_chunk(source, chunk, MAX_CHUNK_SIZE)) { Raise(PyExc_EOFError, ""); }
	result = PyTuple_Pack(3,
		PyLong_FromUnsignedLong(chunk->offset),
		PyInt_FromLong(chunk_digest(chunk)),
		PyString_FromStringAndSize((char*)chunk->data, chunk->length));
	chunk_delete(chunk);
	return result;
}

static char hashsplit_read_chunk_doc[] = "read_chunk(file)\n\nSplit a file into chunks.";

static PyMethodDef hashsplit_methods[] = {
	{"read_chunk", hashsplit_read_chunk, METH_VARARGS, hashsplit_read_chunk_doc},
	{NULL, NULL}
};

PyMODINIT_FUNC init_hashsplit(void) {
	PyObject *mod;
	mod = Py_InitModule3("_hashsplit", hashsplit_methods, "Split a file into chunks ala rsync");
	PyModule_AddObject(mod, "MIN_CHUNK_SIZE", PyInt_FromLong(MIN_CHUNK_SIZE));
}
