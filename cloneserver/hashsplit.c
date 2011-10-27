#include <string.h>
#include <stdio.h>
#include <stdint.h>

#define WINDOWSIZE 128
#define SMALLEST WINDOWSIZE //Must be WINDOWSIZE or bigger
#define BIGGEST 20480
#define DATASIZE BIGGEST
#define MATCHBITS = 13
#define MATCHMASK = (1<<MATCHBITS)-1
#define CHAR_OFFSET 31
#define DIGEST(a,b) (a << 16) | b

typedef struct {
	unsigned long int offset;
	uint16_t s1, s2;
	unsigned int length;
	uint8_t data[DATASIZE];
} Chunk;

static void chunk_init(Chunk *self, int offset) {
	self->offset = offset;
	self->s1 = WINDOWSIZE * CHAR_OFFSET;
	self->s2 = (uint16_t)(WINDOWSIZE * (WINDOWSIZE-1) * CHAR_OFFSET);
	self->length = 0;
}

unsigned int chunk_digest(Chunk *self) {
	return (self->s1 << 16) | self->s2;
}

int chunk_append(Chunk *self, unsigned char add) {
	int cursor = self->length - WINDOWSIZE;
	//Don't bother zeroing memory...
	uint8_t drop = (cursor >= 0) ? self->data[cursor] : 0 ;
	self->data[self->length++] = add;
	self->s1 += add - drop;
	self->s2 += self->s1 - WINDOWSIZE * (drop + CHAR_OFFSET);
	return (self->length < BIGGEST);
	//Returns true if we can add more to this chunk
}

unsigned read_chunk(FILE *source, Chunk *chunk) {
	int buf;
	chunk_init(chunk, ftell(source));
	while (~(chunk_digest(chunk)) & 0x1fff || chunk->length < SMALLEST) {
		if ((buf = fgetc(source))==EOF)
			return (chunk->length > 0); //No more if this chunk has nothing
		if (!(chunk_append(chunk, (char)(buf & 0xff))))
			return 1; //Chunk has data, but it's too big to take more
	}
	return 1;
}

int main(int argc, char* argv[]) {
	FILE *source_file;
	Chunk chunk;
	if ((argc == 1) || (strcmp(argv[1],"-") == 0)) {
		source_file = stdin;
	} else if (!(source_file = fopen(argv[1], "rb"))) {
		fprintf(stderr, "%s: Unable to open file", argv[0]);
		return 1;
	}
	while (read_chunk(source_file, &chunk)) {
		printf("%lu\t%u\t%08x\n", chunk.offset,
			   chunk.length, chunk_digest(&chunk));
	}
	return 0;
}
