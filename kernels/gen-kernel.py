#!/usr/bin/env python3
# Copyright (c) 2020-2024, Intel Corporation
# Author: Ahmad Yasin
#
#   This program is free software; you can redistribute it and/or modify it under the terms and conditions of the
# GNU General Public License, version 2, as published by the Free Software Foundation.
#   This program is distributed in the hope it will be useful, but WITHOUT # ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

# generate C-language kernels with ability to incorporate x86 Assembly with certain control-flow constructs
#
from __future__ import print_function
__author__ = 'ayasin'
__version__ = 0.86
# TODO:
# - functions/calls support
# - make r9/r10 a list-of-2 arg so user can change them

import argparse, os, re, sys
import jumpy as J, references

sys.path.append(os.path.dirname(os.path.realpath(__file__)) + '/..')
import common as C
from lbr.x86 import x86_asm, INST_1B, INST_UNIQ

ap = argparse.ArgumentParser()
ap.add_argument('-n', '--unroll-factor', type=int, default=3, help='# times to repeat instruction(s), aka unroll-factor')
ap.add_argument('-r', '--registers', type=int, default=0, help="# of registers to traverse via '@' if > 0")
ap.add_argument('--registers-max', type=int, default=16, help="max # of registers in the instruction-set")
ap.add_argument('-i', '--instructions', nargs='+', default=[INST_UNIQ], help='Instructions for the primary loop (Loop). '
                'NOP#3 denotes NOP three times. Instructions are read from filename.txt, if solely provided.')
ap.add_argument('-l', '--loops', type=int, default=1, help='# of nested loops')
ap.add_argument('-p', '--prolog-instructions', nargs='+', default=[], help='Instructions prior to the Loop')
ap.add_argument('-e', '--epilog-instructions', nargs='+', default=[], help='Instructions post the Loop')
ap.add_argument('-a', '--align' , type=int, default=0, help='align Loop and target of jumps [in power of 2]')
ap.add_argument('-o', '--offset', type=int, default=0, help='offset unrolled Loop bodies [in bytes]')
ap.add_argument('--label-prefix', default='Lbl', help="Starting '@' implies local labels. empty '' implies numbers-only labels")
ap.add_argument('mode', nargs='?', choices=['basicblock']+J.jumpy_modes, default='basicblock')
ap.add_argument('--mode-args', default='', help="args to pass-through to mode's sub-module")
ap.add_argument('--reference', default=None, help="ID of a reference paper (prints a message)")
ap.add_argument('--init-regs', nargs='+', default=[], help='registers to initialize to non-zero before primary loop e.g. rax')
ap.add_argument('--modify-regs', action='store_const', const=True, default=False, help="enable modifying generator registers")
args = ap.parse_args()

def jumpy(): return args.mode in J.jumpy_modes

def error(x):
  C.printf(x)
  sys.exit(' !\n')

if args.label_prefix == '':
  if args.mode == 'jumpy-random': args.mode_args += '%snumbers-labels=1'%(',' if len(args.mode_args) else '')
  else: error('empty label-prefix is supported with jumpy-random mode only')
prefetch = J.init(args.mode, args.unroll_factor, args.mode_args) if jumpy() else None

if args.registers > 0:
  if '@' not in ' '.join(args.instructions): error("expect '@' in --instructions")
  if args.registers > args.registers_max:    error("invalid value for --registers! must be < %d"%args.registers_max)

if len(args.instructions) == 1 and args.instructions[0].endswith('.txt'):
  f, insts, ip_idx = args.instructions[0], [], 0
  print('// reading instructions from file: %s' % f)
  lines = C.file2lines(f, True)
  for i in lines[:-1]:
    if i.startswith('j') and '0x' in i: i = ' '.join((i.split()[0], 'Lbl_end'))
    x = re.search(r'([0-9a-fx]+)\(%[re]ip', i)
    if x:
      i = i.replace(x.group(1), '0x%x' % (0x100 + ip_idx))
      ip_idx += 16
    insts += [i]
  args.instructions = insts
  args.unroll_factor = 1

if not args.modify_regs:
  for i in args.instructions:
    dst = i.split()[-1]
    if '%r9' in dst or '%r10' in dst: error("can't write to registers r9 and r10, please use other registers")

paper = '"Reference: %s"' % references.Papers[args.reference] if args.reference else str(0)

def itemize(insts):
  if '#' not in ' '.join(insts): return insts
  out=[]
  for i in insts:
    if '#' in i and '+' not in i:
      l = i.split('#')
      if len(l)!=2 or not l[1].isdigit(): error('itemize(): Invalid syntax: %s'%i)
      n=int(l[1])
      out += [l[0] for x in range(n)]
    else: out.append(i)
  #C.annotate(out, 'aft')
  return out

def asm(x, tabs=1, spaces=8+4*(args.loops-1)):
  if ';' in x:
    for i in x.split(';'): print(x86_asm(i, tabs, spaces))
  else: print(x86_asm(x, tabs, spaces))

def label(n, declaration=True, local=False):
 lbl = '%s%05d'%(args.label_prefix, n) if isinstance(n, int) else n
 if args.label_prefix.startswith('@'):
   local = True
   lbl = '%s%05d'%(args.label_prefix[1:], n)
 if declaration:
   if local: return '.local %s\\n"\n\t    "%s:'%(lbl, lbl)
   else:     return lbl+':'
 else:
   return ' '+lbl


#kernel's Header
print("""// Auto-generated by %s's %s version %s invoked with:
// %s
// Do not modify!
//
%s
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#define MSG %s

int main(int argc, const char* argv[])
{
    register uint64_t n asm ("r10");
    register uint64_t i0 asm ("r9");
    if (argc<2) {
        printf("%%s: missing <num-iterations> arg!\\n", argv[0]);
        exit(-1);
    }
    if (MSG) printf("%%s\\n", MSG ? MSG : "");
    asm ("      mov %%1,%%0"
                 : "=r" (n)
                 : "r" (atol(argv[1])));"""%(__author__, C.arg(0), str(__version__), str(args).replace('Namespace', ''),
  '/* %s\n */'%references.Comments[args.reference].replace('\n', '\n * ') if args.reference else '', paper))
for x in vars(args).keys():
  if 'instructions' in x:
    setattr(args, x, itemize(getattr(args, x)))
vec = False
for reg in args.init_regs:
  reg = reg.lower()
  if C.any_in(['xmm', 'ymm', 'zmm'], reg):
    if not vec:
      args.prolog_instructions.append('mov $10,%r11d')
      vec = True
    args.prolog_instructions.append('%s %%r11d,%%%s' % ('movd' if 'xmm' in reg else 'vpbroadcastd', reg))
  else: args.prolog_instructions.append('mov $10,%%%s' % reg)
for inst in [INST_UNIQ] + args.prolog_instructions: asm(inst, spaces=4)

#kernel's Body
for l in range(args.loops):
  if l == args.loops-1 and args.align: asm('.align %d'%(2 ** args.align), tabs=0, spaces=8+4*l)
  print(' '*4*(l+1) + 'for (' + ('' if l==0 else 'uint64_t ') + '%s=0; %s<n; %s++) {' % (('i%d'%l,)*3))
for j in range(args.unroll_factor):
  if args.offset:
     for k in range(j+args.offset-1): asm(INST_1B)
  if jumpy(): asm(label(j), tabs=0)
  for r in range(max(args.registers, 1)):
    for inst in args.instructions:
      if inst in ['PF+JMP', 'JMP', 'JL', 'JG'] or inst.startswith('PF+NOP'):
        if 'PF+' in inst:
          assert prefetch, "was --mode-args set properly?"
          if prefetch['rate']==0 or (j % prefetch['rate'])==0:
            asm('%s%s(%%rip)'%(prefetch['prefetch-inst'], label(J.next(prefetch=True), False)))
          if '#' in inst:
            assert inst.endswith('+JMP'), r"support only 'PF+NOP#\d+JMP' pattern"
            asm(';'.join(itemize(C.chop(inst, ('', 'PF+', '+JMP')).split('+'))))
          inst = 'JMP'
        inst += label(J.next(), False)
      if args.registers and '@' in inst:
        for i in range(9):
          inst = inst.replace('@+%d'%(i+1), str((r+i+1) % args.registers_max))
          inst = inst.replace('@-%d'%(i+1), str((r-i-1) % args.registers_max))
        inst = inst.replace('@', str(r))
      asm(inst)
  if jumpy() and args.align: asm('.align %d'%(2 ** args.align), tabs=0)
if jumpy(): asm(label(args.unroll_factor), tabs=0)
for l in range(args.loops, 0, -1):
  print(' '*4*l + "}")

#kernel's Footer
for inst in args.epilog_instructions: asm(inst, spaces=4)
print("""    asm(".align 512; %s_end:");

    return 0;
}"""%args.label_prefix.replace('@', ''))

