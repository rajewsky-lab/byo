import lz4framed as Z
import os,sys
from time import time
import logging

def chunks(fname, chunksize):
    f = file(fname,'rb')
    chunk = f.read(chunksize)
    while chunk:
        yield chunk
        chunk = f.read(chunksize)

MB = 1024.**2


class LZFile(object):
    
    def __init__(self, fname, max_cached = 1000, compress_on_open=False):
        self.logger = logging.getLogger("LZFile({0})".format(fname) )
        self.basename = fname
        ind_file = fname + '.lzot'
        lz_file = fname + '.lzoc'
        if not os.path.exists(lz_file) and os.path.exists(ind_file):
            if compress_on_open:
                self.compress_file(fname)
            else:
                msg ="The file {0} is not LZ4 compressed and 'compress_on_open' was not set.".format(fname)
                self.logger.error(msg)
                raise IOError(msg)
            
        self.load_index(ind_file)
        self.lz_file = file(lz_file,'rb')
        self.chunk_cache = {}
        self.max_cached = max_cached
        
    @staticmethod
    def compress_file( fname, chunksize=1*1024*1024):
        tab_file = file(fname + '.lzot','w')
        comp_file = file(fname + '.lzoc','wb')
        comp_base = 0
        cum_size = 0
        t0 = time()
        
        tab_file.write('{0}\n'.format(chunksize))

        for chunk in chunks(fname, chunksize):
            uncomp_size = len(chunk)

            t1 = time()
            comp = Z.compress(chunk, level=2)
            comp_size = len(comp)
            comp_file.write(comp)
            ratio = 100. * float(comp_size) / uncomp_size 
            t2 = time()
            throughput = cum_size / (t2-t0)

            tab_file.write('{0}\n'.format(comp_base))
            comp_base += comp_size
            cum_size += uncomp_size

            logging.debug("compressed {0}MB ({1:.1f}%) in {2:.1f} sec, {3:.2f} MB/s  sec".format(chunksize/MB, ratio, t2-t1, throughput/MB))

        tab_file.write('{0}\n'.format(comp_base))
        tab_file.write('{0}\n'.format(cum_size))

    def load_index(self, idxname):
        self.logger.info("loading index '{0}'".format(idxname))
        lines = file(idxname).readlines()
        self.chunk_size = int(lines[0])
        self.L = int(lines[-1])
        self.chunk_starts = [int(b) for b in lines[1:-1]]
        
    def get_chunk(self, i):
        self.lz_file.seek(self.chunk_starts[i])
        comp = self.lz_file.read(self.chunk_starts[i+1] - self.chunk_starts[i])
        return Z.decompress(comp)
    
    def get_chunk_cached(self, i):
        if not i in self.chunk_cache:
            self.chunk_cache[i] = self.get_chunk(i)
            #self.cached_items.append(i)

        if len(self.chunk_cache) > self.max_cached:
            pass
            # not implemented yet: efficient way to discard least used chunks
            
        return self.chunk_cache[i]
            
    def __getslice__(self, start, end):
        cs = self.chunk_size
        out = []
        for chunk_i in range(start / cs, (end / cs) + 1):

            chunk_start = chunk_i * cs
            
            c_start = max(start - chunk_start, 0)
            c_end = min(end - chunk_start, cs)
            #print "CHUNK_I", chunk_i, c_start, c_end, cs
            
            out.append(self.get_chunk_cached(chunk_i)[c_start:c_end])
            
        return "".join(out)

    def __iter__(self):
        self.logger.debug("iterating over lines")
        lines = [""]
        for i in xrange(len(self.chunk_starts) -1):
            chunk = self.get_chunk(i)
            self.logger.debug("iterating over chunk of {0} bytes".format(len(chunk)))
            
            new_lines = chunk.splitlines(True)
            if not lines[-1].endswith('\n'):
                # last line from previous chunk was incomplete.
                lines[-1] += new_lines.pop(0)
                
            lines.extend(new_lines)
            for l in lines[:-1]:
                #self.logger.debug("yielding line of {0} bytes".format(len(l)))
                yield l
                
            lines = lines[-1:]

        for l in lines:
            yield l
            