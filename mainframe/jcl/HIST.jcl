//@HLQ@H JOB (1),'MIG HISTORY',CLASS=@CLASS@,MSGCLASS=@MSGCLASS@,
//         MSGLEVEL=(1,1),USER=@HLQ@,PASSWORD=@PASSWORD@
//*-------------------------------------------------------------------
//* HIST - audit history: BREXX reads the VSAM KSDS MIG.AUDIT.KSDS
//* with VSAMIO (one line per batch), then IDCAMS prints the raw
//* records of both audit clusters. Read-only.
//*-------------------------------------------------------------------
//HISTRX   EXEC RXBATCH,EXEC=MIGHIST,SLIB='@HLQ@.MIG.REXX'
//EXEC.AUDIT DD DSN=@HLQ@.MIG.AUDIT.KSDS,DISP=SHR
//PRINT    EXEC PGM=IDCAMS,COND=EVEN
//SYSPRINT DD SYSOUT=*
//SYSIN    DD *
 PRINT INDATASET(@HLQ@.MIG.AUDIT.KSDS) CHARACTER
 PRINT INDATASET(@HLQ@.MIG.EXCLOG.KSDS) CHARACTER COUNT(50)
/*
//
