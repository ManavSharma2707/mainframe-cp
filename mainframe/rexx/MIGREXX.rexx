/* REXX */
/*********************************************************************/
/* MIGREXX - REXX step of job MIGRUN (BREXX/370 on TK5)              */
/* 1. counts the raw source and target extracts (independent check) */
/* 2. reads the COBOL control record and the exception file         */
/* 3. drops repeated exception rows, sorts them by type + key       */
/* 4. cross-checks every count and takes the decision               */
/* 5. writes: sorted exceptions, report, machine-readable result,   */
/*    audit records for the two VSAM KSDS (batch log, exception log)*/
/* Exit: 0 approved, 4 approved with warning (identical duplicates), */
/*       8 rejected, 12 aborted (controls disagree), 16 REXX failure */
/* DD in : SRCRAW TGTRAW CTLIN EXCIN                                 */
/* DD out: EXCSORT REPORT MIGOUT AUDREC EXCREC                       */
/* Note  : no vertical-bar characters are used on purpose (they are  */
/*         garbled by the ASCII to EBCDIC card-reader translation).  */
/*********************************************************************/
numeric digits 20
signal on syntax name FATAL
signal on novalue name FATAL

sd = date('S')
bid = 'B'sd''space(translate(time('N'),' ',':'),0)
rundate = substr(sd,1,4)'-'substr(sd,5,2)'-'substr(sd,7,2) time('N')

/* ---- 1. independent record counts of the raw extracts ----------- */
call ReadAll 'SRCRAW'
rawsrc = io.0
call ReadAll 'TGTRAW'
rawtgt = io.0

/* ---- 2. control record written by MIGMATCH ---------------------- */
call ReadAll 'CTLIN'
if io.0 < 1 then call Die 'CTLIN IS EMPTY'
rec = left(io.1, 150)
tag    = substr(rec, 1, 8)
c_read = Num(substr(rec,  9, 10))
c_uniq = Num(substr(rec, 19, 10))
c_dsam = Num(substr(rec, 29, 10))
c_dcon = Num(substr(rec, 39, 10))
c_tgt  = Num(substr(rec, 49, 10))
c_mat  = Num(substr(rec, 59, 10))
c_mis  = Num(substr(rec, 69, 10))
c_mss  = Num(substr(rec, 79, 10))
c_ext  = Num(substr(rec, 89, 10))
src_tot = Money(substr(rec,  99, 16))
tgt_tot = Money(substr(rec, 115, 16))
reason = strip(substr(rec, 131, 20))

/* ---- 3. exceptions: drop repeats, rank, sort -------------------- */
call ReadAll 'EXCIN'
seen. = 0
mk.   = 0
nx = 0
x_mss = 0
x_ext = 0
x_mis = 0
x_dup = 0
do i = 1 to io.0
   line = left(io.i, 100)
   if strip(line) = '' then iterate
   if seen.line = 1 then iterate
   seen.line = 1
   typ = strip(substr(line, 19, 8))
   rk = 0
   if typ = 'MISSING'  then rk = 1
   if typ = 'MISMATCH' then rk = 2
   if typ = 'EXTRA'    then rk = 3
   if typ = 'DUPKEY'   then rk = 4
   if rk = 0 then call Die 'UNKNOWN EXCEPTION TYPE' typ
   nx = nx + 1
   xl.nx = line
   xk.nx = rk'-'substr(line,1,18)'-'substr(line,27,8)
   if rk = 1 then x_mss = x_mss + 1
   if rk = 3 then x_ext = x_ext + 1
   if rk = 4 then x_dup = x_dup + 1
   if rk = 2 then do
      mkey = substr(line,1,18)
      if mk.mkey = 0 then do
         mk.mkey = 1
         x_mis = x_mis + 1
      end
   end
end
call ShellSort

/* ---- 4. cross-checks and decision ------------------------------- */
problem = ''
if tag <> 'MIGCTRL ' then problem = 'COBOL ABORT:' reason
if problem = '' then do
   if rawsrc <> c_read then
      problem = 'SOURCE COUNT: EXTRACT' rawsrc 'COBOL' c_read
   else if rawtgt <> c_tgt then
      problem = 'TARGET LOAD REJECTED' rawtgt - c_tgt 'RECORD(S)'
   else if c_uniq + c_dsam + c_dcon <> c_read then
      problem = 'UNIQUE+DUPLICATES <> RECORDS READ'
   else if c_mat + c_mis + c_mss <> c_uniq then
      problem = 'MATCHED+MISMATCH+MISSING <> UNIQUE SOURCE'
   else if c_mat + c_mis + c_ext <> c_tgt then
      problem = 'MATCHED+MISMATCH+EXTRA <> TARGET COUNT'
   else if x_mss <> c_mss then problem = 'MISSING ROWS <> CONTROL'
   else if x_ext <> c_ext then problem = 'EXTRA ROWS <> CONTROL'
   else if x_mis <> c_mis then problem = 'MISMATCH ROWS <> CONTROL'
   else if x_dup <> c_dcon then problem = 'DUPKEY ROWS <> CONTROL'
end

dups = c_dsam + c_dcon
if problem <> '' then do
   finalrc = 12
   decision = 'ABORTED'
   msg = 'HOLD - CONTROLS DISAGREE OR INPUT INVALID'
end
else if c_mss + c_ext + c_mis + c_dcon > 0 then do
   finalrc = 8
   decision = 'REJECTED'
   msg = 'DO NOT CUT OVER'
end
else if c_dsam > 0 then do
   finalrc = 4
   decision = 'WARNING'
   msg = 'SAFE TO CUT OVER - IDENTICAL DUPLICATES WERE DROPPED'
end
else do
   finalrc = 0
   decision = 'APPROVED'
   msg = 'SAFE TO CUT OVER'
end

/* ---- 5. sorted exception dataset -------------------------------- */
do i = 1 to nx
   out.i = xl.i
end
out.0 = nx
call WriteAll 'EXCSORT'

/* ---- 6. human readable report (FBA 133) ------------------------- */
rpn = 0
call Put '1MIGRATION VALIDATION REPORT'
call Put ' Legacy-to-Modern Data Migration Validator  (TK5 / MVS 3.8J)'
call Put ' '
call Put ' BATCH ID  :' bid
call Put ' RUN DATE  :' rundate
call Put ' DECISION  :' decision '(RC' finalrc')  'msg
if problem <> '' then call Put ' REASON    :' problem
call Put ' '
call Put '0RECONCILIATION'
call Put '   Source records in extract .....' right(Comma(rawsrc),10)
call Put '   Identical duplicates dropped ..' right(Comma(c_dsam),10)
call Put '   Conflicting duplicate keys ....' right(Comma(c_dcon),10)
call Put '   Unique source records .........' right(Comma(c_uniq),10)
call Put '   Target records in extract .....' right(Comma(rawtgt),10)
call Put '   Target records in VSAM KSDS ...' right(Comma(c_tgt),10)
call Put '   Matched .......................' right(Comma(c_mat),10)
call Put '   Mismatched records ............' right(Comma(c_mis),10)
call Put '   Missing in target .............' right(Comma(c_mss),10)
call Put '   Extra in target ...............' right(Comma(c_ext),10)
ok1 = 'FAILED'
if c_mat + c_mis + c_mss = c_uniq then ok1 = 'OK'
ok2 = 'FAILED'
if c_mat + c_mis + c_ext = c_tgt then ok2 = 'OK'
ok3 = 'FAILED'
if rawtgt = c_tgt then ok3 = 'OK'
call Put ' '
call Put '   Check: matched+mismatched+missing = unique source :' ok1
call Put '   Check: matched+mismatched+extra   = target        :' ok2
call Put '   Check: target extract = target KSDS (no rejects)  :' ok3
call Put ' '
call Put '0BALANCE CONTROL TOTALS (information only)'
call Put '   Source total ...' right(format(src_tot,,2),18)
call Put '   Target total ...' right(format(tgt_tot,,2),18)
call Put '   Difference .....' right(format(tgt_tot - src_tot,,2),18)
call Put ' '
call Put '0EXCEPTIONS SORTED BY TYPE AND KEY ('nx 'rows)'
call Put ' '
hdr = ' 'left('TYPE',9)left('CUST-ID',9)left('ACCT-NO',11)
hdr = hdr''left('FIELD',9)left('SOURCE VALUE',31)'TARGET VALUE'
call Put hdr
do i = 1 to nx
   l = xl.i
   dl = ' 'left(substr(l,19,8),9)left(substr(l,1,8),9)
   dl = dl''left(substr(l,9,10),11)left(substr(l,27,8),9)
   dl = dl''left(substr(l,35,30),31)substr(l,65,30)
   call Put dl
end
call Put ' '
call Put ' *** END OF REPORT ***'
do i = 1 to rpn
   out.i = left(rp.i, 133)
end
out.0 = rpn
call WriteAll 'REPORT'

/* ---- 7. machine readable result (printed; parsed by Python) ----- */
on = 0
call Mo 'MIGOUT-BEGIN'
call Mo 'BATCH_ID='bid
call Mo 'DECISION='decision
call Mo 'RC='finalrc
call Mo 'SRC_RAW='rawsrc
call Mo 'DUPS='dups
call Mo 'DUP_SAME='c_dsam
call Mo 'DUP_CONF='c_dcon
call Mo 'SRC_UNIQUE='c_uniq
call Mo 'TGT_RAW='rawtgt
call Mo 'TGT_CNT='c_tgt
call Mo 'MATCHED='c_mat
call Mo 'MISMATCH='c_mis
call Mo 'MISSING='c_mss
call Mo 'EXTRA='c_ext
call Mo 'SRC_BAL_TOT='format(src_tot,,2)
call Mo 'TGT_BAL_TOT='format(tgt_tot,,2)
call Mo 'REASON='problem
call Mo 'RUN_DATE='rundate
do i = 1 to nx
   call Mo 'EXC:'xl.i
end
call Mo 'MIGOUT-END'
do i = 1 to on
   out.i = left(mo.i, 133)
end
out.0 = on
call WriteAll 'MIGOUT'

/* ---- 8. audit record for MIG.AUDIT.KSDS (key = batch id) -------- */
kr = left(bid, 15)left(decision, 10)right(finalrc, 3, '0')
kr = kr''right(rawsrc,10,'0')right(dups,10,'0')right(c_uniq,10,'0')
kr = kr''right(c_tgt,10,'0')right(c_mat,10,'0')right(c_mis,10,'0')
kr = kr''right(c_mss,10,'0')right(c_ext,10,'0')
out.1 = left(kr, 120)
out.0 = 1
call WriteAll 'AUDREC'

/* ---- 9. exception log for MIG.EXCLOG.KSDS (key = batch + seq) --- */
do i = 1 to nx
   out.i = left(bid, 15)right(i, 5, '0')left(xl.i, 100)
end
out.0 = nx
call WriteAll 'EXCREC'

say 'MIGREXX BATCH' bid 'DECISION' decision 'RC' finalrc
if problem <> '' then say 'MIGREXX REASON:' problem
exit finalrc

/* ================================================================= */
/* helpers                                                           */
/* ================================================================= */
Put:
   rpn = rpn + 1
   rp.rpn = arg(1)
   return

Mo:
   on = on + 1
   mo.on = arg(1)
   return

ShellSort:
   gap = nx % 2
   do while gap > 0
      do si = gap + 1 to nx
         tk = xk.si
         tl = xl.si
         sj = si
         do while sj > gap
            sp = sj - gap
            if xk.sp >> tk then do
               xk.sj = xk.sp
               xl.sj = xl.sp
               sj = sp
            end
            else leave
         end
         xk.sj = tk
         xl.sj = tl
      end
      gap = gap % 2
   end
   return

Num: procedure
   parse arg s
   s = strip(s)
   if s = '' then call Die 'EMPTY NUMBER'
   if verify(s, '0123456789') > 0 then call Die 'BAD NUMBER' s
   return s + 0

Money: procedure
   parse arg s
   sgn = left(s, 1)
   digs = substr(s, 2)
   if sgn <> '+' then if sgn <> '-' then call Die 'BAD SIGN IN TOTAL' s
   if digs = '' then call Die 'EMPTY TOTAL'
   if verify(digs, '0123456789') > 0 then call Die 'BAD TOTAL' s
   v = digs / 100
   if sgn = '-' then v = -v
   return v

Comma: procedure
   parse arg n
   s = strip(n)
   o = ''
   do while length(s) > 3
      o = ','right(s, 3)o
      s = left(s, length(s) - 3)
   end
   return s''o

Die:
   say 'MIGREXX ERROR:' arg(1)
   exit 16

FATAL:
   say 'MIGREXX FAILED AT LINE' sigl
   exit 16

/* ==IO-BEGIN== (the local unit tests replace everything below) */
ReadAll:
   parse arg zzdd
   io.0 = 0
   "EXECIO * DISKR" zzdd "(STEM io."
   if rc <> 0 then call Die 'EXECIO READ RC' rc 'DD' zzdd
   return

WriteAll:
   parse arg zzdd
   "EXECIO * DISKW" zzdd "(STEM out."
   if rc <> 0 then call Die 'EXECIO WRITE RC' rc 'DD' zzdd
   return
/* ==IO-END== */
