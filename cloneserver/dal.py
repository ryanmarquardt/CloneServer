#!/usr/bin/env python

import collections
import sqlite3
import re

from contextlib import contextmanager

class attrdict(dict): __getattr__,__setattr__,__delattr__ = dict.__getitem__,dict.__setitem__,dict.__delitem__

class namedlist(collections.MutableMapping, collections.MutableSequence):
	name = 'namedlist'
	def __init__(self, *items):
		self._keys, self._values, self._indices = [], [], {}
		for key, val in items:
			self.__setitem__(key, val)

	def _which(self, i):
		return i if isinstance(i, int) else self._indices[i]

	def __len__(self):
		return len(self._keys)

	def __iter__(self):
		return iter(self._keys)

	def __getitem__(self, i):
		return self._values[self._which(i)]

	def __setitem__(self, key, value):
		try:
			i = self._which(key)
		except KeyError:
			if isinstance(key, int):
				raise KeyError
			else: #dict insert
				self._indices[key] = len(self._keys)
				self._keys.append(key)
				self._values.append(value)
		else: #list or dict replace
			self._values[i] = value

	def __delitem__(self, key):
		i = self._which(key)
		if i is None:
			raise KeyError
		else:
			del self._keys[i]
			del self._values[i]
			self._indices = dict((key,i) for i,key in enumerate(self._keys))

	def insert(self, i, (key,val)):
		self._keys.insert(i, key)
		self._values.insert(i, val)
		self._indices = dict((key,i) for i,key in enumerate(self._keys))

	def __repr__(self):
		return '%s(%s)' % (self.name,', '.join('%s=%r' % (k, self[k]) for k in self.keys()))
	def as_dict(self):
		return dict(zip(self._keys, self._values))
	__str__ = __repr__

class Row(namedlist):
	name='Row'
	def __init__(self, values, description):
		namedlist.__init__(self, *zip((d[0] for d in description), values))

class DALError(Exception): pass
class UnknownDatabase(DALError): pass
class UniqueKeyConflict(DALError): pass
class IllegalIdentifier(DALError): pass

def sanitize(ident, star=False):
	if star and ident == '*':
		return ident
	if star and ',' in ident:
		idents = ident.split(',')
	else:
		idents = [ident]
	for ident in idents:
		match = re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', ident)
		if match is None or match.span() != (0,len(ident)):
			raise IllegalIdentifier(repr(ident))
	return ','.join(idents)

class Query(object):
	def __init__(self, tables, sql, val):
		self.tables, self.sql, self.val = tables, sql, val
	def __or__(a, b):
		return Query(a.tables | b.tables, a.sql + ' or ' + b.sql, a.val + b.val)
	def __and__(a, b):
		return Query(a.tables | b.tables, a.sql + ' and ' + b.sql, a.val + b.val)
	def __invert__(self):
		return Query(self.tables | q.tables, 'not ' + self.sql, self.val)

class Rows(collections.Iterator):
	def __init__(self, cursor, fields):
		self._cursor = cursor
		self._fields = fields

	def __len__(self):
		return self._cursor.rowcount

	def next(self):
		row = self._cursor.fetchone()
		if row is None: raise StopIteration
		return Row(row, self._cursor.description)

	def as_list(self):
		return list(row.as_dict() for row in self)

class Set(object):
	def __init__(self, db, query):
		self._db = db
		self._query = query

	def select(self, *fields, **kwargs):
		sql = 'SELECT {distinct} {fields} FROM {tables} {where_clause};'.format(
			distinct='DISTINCT' if kwargs.get('distinct') else '',
			fields=','.join(sanitize(f._name, star=True) for f in fields),
			tables=','.join(set(field._table._name for field in fields)),
			where_clause='WHERE '+self._query.sql if self._query else '',
			)
		values = self._query.val if self._query else ()
		return Rows(self._db.executesql(sql, values), fields)

	def delete(self):
		sql = 'DELETE FROM {tables} {where_clause};'.format(
			tables=','.join(self._query.tables),
			where_clause='WHERE '+self._query.sql if self._query else '',
			)
		values = self._query.val if self._query else ()
		return Rows(self._db.executesql(sql, values), fields)

	def update(self, **values):
		sql = 'UPDATE OR FAIL {tables} SET {set_clause} {where_clause}'.format(
			tables=','.join(self._query.tables),
			set_clause=','.join('%s=?' % sanitize(k) for k in values),
			where_clause='WHERE '+self._query.sql if self._query else '',
			)
		vals = values.values() + (self._query.val if self._query else ())
		with self._db:
			self._db.executesql(sql, values)

class Field(object):
	def __init__(self, name, type=str, convert=None, serialize=None,
	             default=None, unique=False, notnull=False, key=False):
		self._name = name
		type = {'TEXT':unicode, 'INTEGER':int, 'REAL':float, 'BLOB':buffer,
			}.get(type,type)
		self._type = {
			str:'TEXT', unicode:'TEXT', 'TEXT':'TEXT',
			int:'INTEGER', long:'INTEGER', 'INTEGER':'INTEGER',
			float:'REAL', 'REAL':'REAL',
			}.get(type, 'BLOB')
		self._unique = unique if not key else False
		self._notnull = notnull if not key else False
		self._convert = convert or type
		self._serialize = serialize or (lambda x:x)
		self._is_key = bool(key)

	def identifier(self):
		return '.'.join((
			sanitize(self._table._name),
			sanitize(self._name, star=True)
			))

	def __str__(self):
		tokens = [sanitize(self._name), sanitize(self._type)]
		if self._unique: tokens.append('UNIQUE')
		if self._notnull: tokens.append('NOT NULL')
		if self._is_key: tokens.append('PRIMARY KEY ON CONFLICT FAIL')
		return ' '.join(tokens)

	def __eq__(self, x): return Query(set((self._table._name,)),
	 '%s=?'  % self.identifier(), (x,))
	def __ne__(self, x): return Query(set((self._table._name,)),
	 '%s!=?' % self.identifier(), (x,))
	def __lt__(self, x): return Query(set((self._table._name,)),
	 '%s<?'  % self.identifier(), (x,))
	def __le__(self, x): return Query(set((self._table._name,)),
	 '%s<=?' % self.identifier(), (x,))
	def __gt__(self, x): return Query(set((self._table._name,)),
	 '%s>?'  % self.identifier(), (x,))
	def __ge__(self, x): return Query(set((self._table._name,)),
	 '%s>=?' % self.identifier(), (x,))

class Table(collections.MutableMapping):
	def __init__(self, db, name, fields):
		self._db = db
		self._name = name
		self.ALL = namedlist()
		self._key_field = None
		for field in fields:
			field._table = self
			self.ALL.append((field._name,field))
			if field._is_key:
				self._key_field = field
		for _name in db.implementation.key_fields:
			if _name not in self.ALL:
				self.id = Field(_name, int)
				self.id._table = self
				break
		self.ALL._name = ','.join(f._name for f in self.ALL.values())
		self.ALL._table = self
		self._key_field = self._key_field or self.id
		with self._db:
			self._db.executesql('CREATE TABLE IF NOT EXISTS %s (%s);' % (
				sanitize(name),
				', '.join(map(str,fields)) #Only declare fields which were passed to us
				))

	def __getattr__(self, name):
		if name.startswith('_') or name in ('ALL','id'):
			return self.__dict__[name]
		else:
			return self.ALL[name]

	def __setattr__(self, name, value):
		if name.startswith('_') or name in ('ALL','id'):
			self.__dict__[name] = value
		else:
			raise NameError("New fields cannot be added after table definition")

	def __getitem__(self, key):
		self._db(self._key_field == key).select(self.ALL)

	def __setitem__(self, key, value):
		if hasattr(value, 'items'):
			values = dict(value.items())
			values[self._key_field._name] = key
		elif hasattr(value, '__iter__'):
			values = dict(zip(self.ALL,value))
		elif len(self.ALL) == 1 or (len(self.ALL==2) and self._key_field in self.ALL):
			value_field = self.ALL[0] if self.ALL[0] != self._key_field else self.ALL[1]
			values = {self._key_field._name:key, value_field._name:value}
		else:
			ValueError('Expected a dict or tuple')
		self.replace(**values)

	def __iter__(self):
		return self._db().select(self._key_field)

	def __len__(self):
		return len(self._db().select(self._key_field))

	def __delitem__(self, key):
		self._db(self._key_field == key).delete()

	def insert(self, **kwargs):
		with self._db:
			self._db.executesql('INSERT OR FAIL INTO %s (%s) VALUES (%s);' % (
				sanitize(self._name),
				','.join(map(sanitize,kwargs.keys())),
				','.join(['?']*len(kwargs)),
				), kwargs.values())

	def replace(self, **kwargs):
		with self._db:
			self._db.executesql('INSERT OR REPLACE INTO %s (%s) VALUES (%s);' % (
				sanitize(self._name),
				','.join(map(sanitize,kwargs.keys())),
				','.join(['?']*len(kwargs)),
				), kwargs.values())

	def drop(self):
		with self._db:
			self._db.executesql('DROP TABLE %s;' % sanitize(self._name))

	def truncate(self):
		with self._db:
			self._db.executesql('DELETE FROM %s;' % sanitize(self._name))

	def import_from_csv_file(self, file):
		file = file if hasattr(file, 'read') else open(file, 'r')
		raise NotImplementedError

class Implementation(object):
	def __init__(self, connect_func, location, key_fields):
		self.connect = connect_func
		self.location = location
		self.key_fields = key_fields

Implementations = {
	'sqlite':Implementation(sqlite3.connect, ':memory:', ['_rowid_', 'oid', 'rowid']),
}
#Use sqlite by default (it's included in the standard library)
Implementations[''] = Implementations['sqlite']

class DB(object):
	def __init__(self, uri=''):
		protocol,sep,location = uri.partition('://')
		self.__impl = Implementations.get(protocol)
		if not self.__impl:
			raise UnknownDatabase(protocol)
		location = location or self.__impl.location
		self._uri = ''.join((protocol,sep,location))
		self.__depth = 0
		self.__conn = self.__impl.connect(location)

	@property
	def implementation(self): return self.__impl

	def __call__(self, query=None):
		return Set(self, query)

	def executesql(self, sql, values=()):
		self._last_sql = sql.replace('?','{!r}').format(*values)
		try:
			return self.__conn.cursor().execute(sql, values)
		except sqlite3.IntegrityError:
			raise UniqueKeyConflict

	def __enter__(self):
		self.__depth += 1
		return self

	def __exit__(self, exc, obj, tb):
		self.__depth -= 1
		if self.__depth == 0:
			self.__conn.commit() if exc is None else self.__conn.rollback()

	def define_table(self, name, *fields):
		table = Table(self, name, fields)
		setattr(self, name, table)
		return table

if __name__=='__main__':
	import traceback
	@contextmanager
	def expect(exc):
		try:
			yield None
		except exc, e:
			print ''.join(traceback.format_exception_only(exc, e)),
		else:
			raise Exception('Expected %s' % exc)

	db = DB('sqlite://')
	print 'Connected to', `db._uri`
	db.define_table('test_table', Field('key', key=True), Field('value'), Field('price', int))
	with expect(IllegalIdentifier):
		db.define_table('test_table2', Field('1'))
	db.test_table.insert(key='a', value='1', price=1)
	db.test_table['b'] = {'value':'2', 'price':1}
	with expect(UniqueKeyConflict):
		db.test_table.insert(key='b', value='3', price=1)
	with db: #Wait to commit or rollback until end of block
		db.test_table['d'] = {'value':'3', 'price':1}
		db.test_table['b'] = {'value':'3', 'price':1}
	db.test_table.replace(key='b', value='3', price=1)
	db.test_table['b'] = {'value':'4', 'price':1}
	db.test_table['c'] = {'value':'3', 'price':1}
	for row in db().select(db.test_table.ALL): print row
	print db.test_table.key
	for row in db(db.test_table.key=='b').select(db.test_table.ALL): print row
	for row in db(db.test_table.value=='3').select(db.test_table.ALL): print row
	for value, price in db(db.test_table.value==3).select(db.test_table.value, db.test_table.price): print row
	print 'Tests finished successfully'
