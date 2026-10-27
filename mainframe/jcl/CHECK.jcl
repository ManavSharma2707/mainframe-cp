//@HLQ@K JOB (1),'MIG CHECK',CLASS=@CLASS@,MSGCLASS=@MSGCLASS@,
//         MSGLEVEL=(1,1),USER=@HLQ@,PASSWORD=@PASSWORD@
//*-------------------------------------------------------------------
//* CHECK - read-only check that this TK5 has what the project needs:
//*   procedures COBUCL, RXBATCH, SORT in SYS2.PROCLIB, BREXX
//*   libraries, a working sort, and the @HLQ@ catalog alias.
//*-------------------------------------------------------------------
//LIST     EXEC PGM=IKJEFT01
//SYSTSPRT DD SYSOUT=*
//SYSTSIN  DD *
 LISTDS 'SYS2.PROCLIB' MEMBERS
 LISTCAT LEVEL(BREXX)
 LISTCAT LEVEL(@HLQ@)
/*
//SORTCHK  EXEC SORT
//SORTIN   DD *
CHECK-B
CHECK-A
/*
//SORTOUT  DD SYSOUT=*,DCB=(RECFM=FB,LRECL=80,BLKSIZE=80)
//SYSIN    DD *
 SORT FIELDS=(1,7,CH,A)
/*
//
