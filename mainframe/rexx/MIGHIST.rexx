/* REXX */
/*********************************************************************/
/* MIGHIST - prints the validation history kept in the VSAM KSDS    */
/* MIG.AUDIT.KSDS (one 120-byte record per batch, key = batch id).  */
/* Uses BREXX/370 VSAMIO (sequential READ NEXT). DD: AUDIT          */
/*********************************************************************/
"VSAMIO OPEN AUDIT (READ"
if rc <> 0 then do
   say 'MIGHIST: cannot open AUDIT (no batch logged yet?) RC' rc
   exit 4
end
say 'MIGHIST-BEGIN'
say left('BATCH ID',16)left('DECISION',10)'RC'right('RAW',8),
    right('DUPS',6)right('UNIQUE',8)right('TARGET',8)right('MATCHED',8),
    right('CHANGED',8)right('MISSING',8)right('EXTRA',6)
n = 0
do forever
   "VSAMIO READ AUDIT (NEXT VAR rec"
   if rc <> 0 then leave
   rec = left(rec, 120)
   n = n + 1
   say 'HIST:'left(substr(rec,1,15),16)left(substr(rec,16,10),10),
       right(substr(rec,26,3)+0,2)right(substr(rec,29,10)+0,8),
       right(substr(rec,39,10)+0,6)right(substr(rec,49,10)+0,8),
       right(substr(rec,59,10)+0,8)right(substr(rec,69,10)+0,8),
       right(substr(rec,79,10)+0,8)right(substr(rec,89,10)+0,8),
       right(substr(rec,99,10)+0,6)
end
"VSAMIO CLOSE AUDIT"
say 'MIGHIST-END' n 'batch(es)'
exit 0
