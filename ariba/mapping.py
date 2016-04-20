import os
import sys
import pysam
import pyfastaq
from ariba import common

class Error (Exception): pass


def bowtie2_index(ref_fa, outprefix, bowtie2='bowtie2', verbose=False, verbose_filehandle=sys.stdout):
    expected_files = [outprefix + '.' + x + '.bt2' for x in ['1', '2', '3', '4', 'rev.1', 'rev.2']]
    file_missing = False
    for filename in expected_files:
        if not os.path.exists(filename):
            file_missing = True
            break 

    if not file_missing:
        return

    cmd = ' '.join([
        bowtie2 + '-build',
        '-q',
        ref_fa,
        outprefix
    ])

    common.syscall(cmd, verbose=verbose, verbose_filehandle=verbose_filehandle)


def run_bowtie2(
      reads_fwd,
      reads_rev,
      ref_fa,
      out_prefix,
      threads=1,
      max_insert=1000,
      sort=False,
      samtools='samtools',
      bowtie2='bowtie2',
      bowtie2_preset='very-sensitive-local',
      verbose=False,
      verbose_filehandle=sys.stdout,
      remove_both_unmapped=False,
      clean_index=True,
    ):

    map_index = out_prefix + '.map_index'

    if clean_index:
        clean_files = [map_index + '.' + x + '.bt2' for x in ['1', '2', '3', '4', 'rev.1', 'rev.2']]
    else:
        clean_files = []

    final_bam = out_prefix + '.bam'
    if sort:
        intermediate_bam = out_prefix + '.unsorted.bam'
    else:
        intermediate_bam = final_bam

    map_cmd = [
        bowtie2,
        '--threads', str(threads),
        '--reorder',
        '--' + bowtie2_preset,
        '-X', str(max_insert),
        '-x', map_index,
        '-1', reads_fwd,
        '-2', reads_rev,
    ]

    if remove_both_unmapped:
        map_cmd.append(r''' | awk ' !(and($2,4)) || !(and($2,8)) ' ''')


    map_cmd.extend([
        '|', samtools, 'view',
        '-bS -T', ref_fa,
        '- >', intermediate_bam
    ])

    map_cmd = ' '.join(map_cmd)

    bowtie2_index(ref_fa, map_index, bowtie2=bowtie2, verbose=verbose, verbose_filehandle=verbose_filehandle)
    common.syscall(map_cmd, verbose=verbose, verbose_filehandle=verbose_filehandle)

    if sort:
        threads = min(4, threads)
        thread_mem = int(500 / threads)
        sort_cmd = ' '.join([
            samtools,
            'sort',
            '-@' + str(threads),
            '-m' + str(thread_mem) + 'M',
            '-o', final_bam,
            '-O bam',
            '-T', out_prefix + '.tmp.samtool_sort',
            intermediate_bam,
        ])
        index_cmd = samtools + ' index ' + final_bam
        common.syscall(sort_cmd, verbose=verbose, verbose_filehandle=verbose_filehandle)
        common.syscall(index_cmd, verbose=verbose, verbose_filehandle=verbose_filehandle)
        clean_files.append(intermediate_bam)

    for fname in clean_files:
        os.unlink(fname)


def get_total_alignment_score(bam):
    '''Returns total of AS: tags in the input BAM'''
    sam_reader = pysam.Samfile(bam, "rb")
    total = 0
    for sam in sam_reader.fetch(until_eof=True):
        try:
            total += sam.opt('AS')
        except:
            pass
    return total


def sam_to_fastq(sam):
    '''Given a pysam alignment, returns the sequence a Fastq object.
       Reverse complements as required and add suffix /1 or /2 as appropriate from the flag'''
    name = sam.qname
    if sam.is_read1:
        name += '/1'
    elif sam.is_read2:
        name += '/2'
    else:
        raise Error('Read ' + name + ' must be first or second of pair according to flag. Cannot continue')

    seq = pyfastaq.sequences.Fastq(name, common.decode(sam.seq), common.decode(sam.qual))
    if sam.is_reverse:
        seq.revcomp()

    return seq


