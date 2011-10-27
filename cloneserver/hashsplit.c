#include <stdio.h>
#include <memory.h>

#define WINDOWSIZE 128
#define CHAR_OFFSET 31
#define DIGEST(a,b) (a << 16) | b

typedef struct {
	unsigned long offset;
	unsigned int length;
	unsigned int digest;
	unsigned int s1, s2;
	unsigned char window[WINDOWSIZE];
	unsigned int window_offset;
} Chunk;

static void chunk_init(Chunk *self, int offset) {
	self->offset = offset;
	self->length = 0;
	self->s1 = WINDOWSIZE * CHAR_OFFSET;
	self->s2 = WINDOWSIZE * (WINDOWSIZE-1) * CHAR_OFFSET;
	self->digest = DIGEST(self->s1,self->s2);
	self->window_offset = 0;
	memset(self->window, 0, WINDOWSIZE);
}

static void chunk_append(Chunk *self, unsigned char add) {
	unsigned char drop = self->window[self->window_offset];
	self->window[self->window_offset] = add;
	self->window_offset = (self->window_offset+1) % WINDOWSIZE;
	self->s1 += add - drop;
	self->s1 &= 0xffff;
	self->s2 += self->s1 - WINDOWSIZE * (drop + CHAR_OFFSET);
	self->s2 &= 0xffff;
	self->digest = DIGEST(self->s1, self->s2);
	self->length += 1;
}

unsigned read_chunk(FILE *source, Chunk *chunk, int smallest, int biggest) {
	int buf;
	if (smallest < WINDOWSIZE) smallest = WINDOWSIZE;
	chunk_init(chunk, ftell(source));
	while (~(chunk->digest) & 0x1fff || chunk->length < smallest) {
		if ((buf = fgetc(source))==EOF) return (chunk->length > 0)?1:0;
		chunk_append(chunk, (char)(buf & 0xff));
		if (biggest && chunk->length >= biggest) return 1;
	}
	return 1;
}

int main(int argc, char* argv[]) {
	FILE *source_file;
	Chunk chunk;
	if (argc > 1) {
		if (!(source_file = fopen(argv[1], "rb"))) {
			fprintf(stderr, "%s: Unable to open file", argv[0]);
			return 1;
		}
		while (read_chunk(source_file, &chunk, 0, 0)) {
			printf("%lu\t%u\t%08x\n", chunk.offset, 
			       chunk.length, chunk.digest);
		}
	} else {
		printf("Usage: %s [file-to-chunk]\n", argv[0]);
	}
	return 0;
}
