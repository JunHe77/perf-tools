#!/usr/bin/env python
# generate C-language kernels with ability to incorporate x86 Assembly with certain control-flow constructs
# Author: Ahmad Yasin
# edited: May. 2021
from __future__ import print_function
__author__ = 'ayasin'
__version__ = 0.52
# TODO:
# - multi-byte NOP support
# - move Paper to a seperate module

import argparse, sys

import jumpy as J

INST_UNIQ='PAUSE'
INST_1B='NOP'
NOP10='nopw   %cs:0x0(%rax,%rax,1)'
NOP14='data16 data16 data16 data16 nopw %cs:0x0(%rax,%rax,1)'
MOVLG='movabs $0x8877665544332211, %r8'
Papers = {
  'MGM':  'A Metric-Guided Method for Discovering Impactful Features and Architectural Insights for Skylake-Based Processors. Ahmad Yasin, Jawad Haj-Yahya, Yosi Ben-Asher, Avi Mendelson. TACO 2019 and HiPEAC 2020.',
}

ap = argparse.ArgumentParser()
ap.add_argument('-n', '--num', type=int, default=3, help='# times to repeat instruction(s), aka unroll-factor')
ap.add_argument('-r', '--registers', type=int, default=0, help="# of registers to traverse via '@' if > 0")
ap.add_argument('--registers-max', type=int, default=16, help="max # of registers in the instruction-set")
ap.add_argument('-i', '--instructions', nargs='+', default=[INST_UNIQ], help='instructions for the primary loop')
ap.add_argument('-p', '--prolog-instructions', nargs='+', default=[], help='instructions prior to the primary loop')
ap.add_argument('-e', '--epilog-instructions', nargs='+', default=[], help='instructions post the primary loop')
ap.add_argument('-a', '--align' , type=int, default=0, help='in power of 2')
ap.add_argument('-o', '--offset', type=int, default=0)
ap.add_argument('--label-prefix', default='Lbl')
ap.add_argument('mode', nargs='?', choices=['basicblock']+J.jumpy_modes, default='basicblock')
args = ap.parse_args()

paper=str(0)
if args.registers > 0:
  if not '@' in ' '.join(args.instructions): sys.exit("expect '@' in --instructions")
  if args.registers > args.registers_max:   sys.exit("invalid value for --registers! must be < %d"%args.registers_max)
  paper='"Reference: %s"'%Papers['MGM']

def asm(x, tabs=1, spaces=8):
  if x == 'MOVLG': x = MOVLG
  print(' '*spaces + 'asm("' + '\t'*tabs + x + '");')

def jumpy(): return args.mode in J.jumpy_modes

def label(n, st=True): return '%s%05d%s'%(('' if st else ' ') + args.label_prefix, n, ':' if st else '')

print("// Auto-generated by %s's %s version %s invoked with:\n//  %s .\n"%(__author__, sys.argv[0].replace('./',''), str(__version__), str(args).replace('Namespace', '')) + """// Do not modify!
//
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#define MSG %s

int main(int argc, const char* argv[])
{
    uint64_t i,n;
    if (argc<2) {
        printf("%%s: missing <num-iterations> arg!\\n", argv[0]);
        exit(-1);
    }
    if (MSG) printf("%%s\\n", MSG ? MSG : "");
    n= atol(argv[1]);"""%paper)
for inst in [INST_UNIQ] + args.prolog_instructions: asm(inst, spaces=4)
if args.align: asm('.align %d'%(2 ** args.align), tabs=0)
print("    for (i=0; i<n; i++) {")
for j in range(args.num):
  if args.offset:
     for k in range(j+args.offset-1): asm(INST_1B)
  if jumpy(): asm(label(j), tabs=0)
  for r in range(max(args.registers, 1)):
    for inst in args.instructions:
      if inst in ['JMP', 'JL']: inst += label(J.next(args.mode, args.num), False)
      if args.registers and '@' in inst:
        for i in range(9):
          inst = inst.replace('@+%d'%(i+1), str((r+i+1) % args.registers_max))
          inst = inst.replace('@-%d'%(i+1), str((r-i-1) % args.registers_max))
        inst = inst.replace('@', str(r))
      asm(inst)
  if jumpy() and args.align: asm('.align %d'%(2 ** args.align), tabs=0)
if jumpy(): asm(label(args.num), tabs=0)
print("    }")

for inst in args.epilog_instructions: asm(inst, spaces=4)

print("""    asm(".align 512; %s_end:");

    return 0;
}"""%args.label_prefix)

