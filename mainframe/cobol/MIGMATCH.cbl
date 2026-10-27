       IDENTIFICATION DIVISION.
       PROGRAM-ID. MIGMATCH.
      *****************************************************************
      * MIGMATCH - match-merge step of job MIGRUN (TK5 / MVS 3.8J)
      * Written for the TK5 ANS COBOL compiler IKFCBL00 (COBOL-68
      * level): no FILE STATUS, no EVALUATE, no END-IF, no FUNCTION.
      *
      * SRCIN   FB 80  legacy extract SORTED by key (duplicates kept)
      * TGTIN   FB 80  target rows unloaded from the target KSDS
      *                (already in key order, keys unique)
      * DEDUP   FB 80  unique source records (cutover payload)
      * EXCOUT  FB 100 one row per exception
      * CTLOUT  FB 150 one control record (counts + balance totals)
      *
      * Key = CUST-ID + ACCT-NO (columns 1-18 in both files).
      * Exception types: MISSING  (key only in source)
      *                  EXTRA    (key only in target)
      *                  MISMATCH (one row per differing field)
      *                  DUPKEY   (same source key, different data)
      * Identical source duplicates are dropped and only counted.
      * RETURN-CODE: 0 finished, 12 aborted (reason in CTL-REASON)
      *****************************************************************
       ENVIRONMENT DIVISION.
       CONFIGURATION SECTION.
       SOURCE-COMPUTER. IBM-370.
       OBJECT-COMPUTER. IBM-370.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT SRC-FILE   ASSIGN TO UT-S-SRCIN.
           SELECT TGT-FILE   ASSIGN TO UT-S-TGTIN.
           SELECT DEDUP-FILE ASSIGN TO UT-S-DEDUP.
           SELECT EXC-FILE   ASSIGN TO UT-S-EXCOUT.
           SELECT CTL-FILE   ASSIGN TO UT-S-CTLOUT.

       DATA DIVISION.
       FILE SECTION.
       FD  SRC-FILE
           RECORDING MODE IS F
           LABEL RECORDS ARE STANDARD
           BLOCK CONTAINS 0 RECORDS
           DATA RECORD IS SRC-REC.
       01  SRC-REC.
           05  SRC-KEY.
               10  SRC-CUST-ID     PIC X(8).
               10  SRC-ACCT-NO     PIC X(10).
           05  SRC-NAME            PIC X(20).
           05  SRC-BAL             PIC 9(9)V99.
           05  SRC-BAL-X REDEFINES SRC-BAL
                                   PIC X(11).
           05  SRC-DATE            PIC X(8).
           05  SRC-STATUS          PIC X(1).
           05  FILLER              PIC X(22).

       FD  TGT-FILE
           RECORDING MODE IS F
           LABEL RECORDS ARE STANDARD
           BLOCK CONTAINS 0 RECORDS
           DATA RECORD IS TGT-REC.
       01  TGT-REC.
           05  TGT-KEY.
               10  TGT-CUST-ID     PIC X(8).
               10  TGT-ACCT-NO     PIC X(10).
           05  TGT-NAME            PIC X(30).
           05  TGT-BAL-TXT.
               10  TGT-BAL-INT     PIC X(9).
               10  TGT-BAL-DOT     PIC X(1).
               10  TGT-BAL-DEC     PIC X(2).
           05  TGT-DATE-TXT.
               10  TGT-D-YYYY      PIC X(4).
               10  TGT-D-SEP1      PIC X(1).
               10  TGT-D-MM        PIC X(2).
               10  TGT-D-SEP2      PIC X(1).
               10  TGT-D-DD        PIC X(2).
           05  TGT-STATUS          PIC X(1).
           05  FILLER              PIC X(9).

       FD  DEDUP-FILE
           RECORDING MODE IS F
           LABEL RECORDS ARE STANDARD
           BLOCK CONTAINS 0 RECORDS
           DATA RECORD IS DEDUP-REC.
       01  DEDUP-REC               PIC X(80).

       FD  EXC-FILE
           RECORDING MODE IS F
           LABEL RECORDS ARE STANDARD
           BLOCK CONTAINS 0 RECORDS
           DATA RECORD IS EXC-REC.
       01  EXC-REC                 PIC X(100).

       FD  CTL-FILE
           RECORDING MODE IS F
           LABEL RECORDS ARE STANDARD
           BLOCK CONTAINS 0 RECORDS
           DATA RECORD IS CTL-REC.
       01  CTL-REC                 PIC X(150).

       WORKING-STORAGE SECTION.
       77  WS-ABORT                PIC X VALUE 'N'.
       77  WS-SRC-EOF              PIC X VALUE 'N'.
       77  WS-TGT-EOF              PIC X VALUE 'N'.
       77  WS-SKIP                 PIC X VALUE 'Y'.
       77  WS-DIFF                 PIC X VALUE 'N'.
       77  WS-TBAL-OK              PIC X VALUE 'N'.
       77  WS-TDATE-OK             PIC X VALUE 'N'.
       77  WS-REASON               PIC X(20) VALUE SPACES.
       77  WS-NEW-REASON           PIC X(20) VALUE SPACES.
       77  WS-SRC-TOT              PIC S9(13)V99 VALUE ZERO.
       77  WS-TGT-TOT              PIC S9(13)V99 VALUE ZERO.

       01  WS-KEYS.
           05  WS-SRC-KEY          PIC X(18) VALUE LOW-VALUES.
           05  WS-TGT-KEY          PIC X(18) VALUE LOW-VALUES.
           05  WS-PREV-SRC-KEY     PIC X(18) VALUE LOW-VALUES.
           05  WS-PREV-TGT-KEY     PIC X(18) VALUE LOW-VALUES.

       01  WS-KEPT-REC.
           05  WS-K-KEY.
               10  WS-K-CUST       PIC X(8).
               10  WS-K-ACCT       PIC X(10).
           05  WS-K-NAME           PIC X(20).
           05  WS-K-BAL            PIC 9(9)V99.
           05  WS-K-BAL-X REDEFINES WS-K-BAL
                                   PIC X(11).
           05  WS-K-DATE           PIC X(8).
           05  WS-K-STATUS         PIC X(1).
           05  FILLER              PIC X(22).

       01  WS-COUNTERS.
           05  WS-SRC-READ         PIC 9(10) VALUE ZERO.
           05  WS-SRC-UNIQUE       PIC 9(10) VALUE ZERO.
           05  WS-DUP-SAME         PIC 9(10) VALUE ZERO.
           05  WS-DUP-CONF         PIC 9(10) VALUE ZERO.
           05  WS-TGT-CNT          PIC 9(10) VALUE ZERO.
           05  WS-MATCHED          PIC 9(10) VALUE ZERO.
           05  WS-MISMATCH         PIC 9(10) VALUE ZERO.
           05  WS-MISSING          PIC 9(10) VALUE ZERO.
           05  WS-EXTRA            PIC 9(10) VALUE ZERO.
           05  WS-EXC-ROWS         PIC 9(10) VALUE ZERO.

       01  WS-TBAL-GRP.
           05  WS-TBAL-INT         PIC 9(9).
           05  WS-TBAL-DEC         PIC 9(2).
       01  WS-TBAL-NUM REDEFINES WS-TBAL-GRP
                                   PIC 9(9)V99.

       01  WS-TDATE-N.
           05  WS-TD-YYYY          PIC X(4).
           05  WS-TD-MM            PIC X(2).
           05  WS-TD-DD            PIC X(2).

       01  WS-VAL-GRP.
           05  WS-V-NAME           PIC X(17).
           05  FILLER              PIC X(1) VALUE SPACE.
           05  WS-V-BAL            PIC Z(8)9.99.
       01  WS-VAL-RAW REDEFINES WS-VAL-GRP.
           05  WS-VR-NAME          PIC X(18).
           05  WS-VR-BAL           PIC X(12).

       01  WS-EDIT-BAL             PIC Z(8)9.99.

       01  WS-EXC.
           05  WS-X-CUST           PIC X(8).
           05  WS-X-ACCT           PIC X(10).
           05  WS-X-TYPE           PIC X(8).
           05  WS-X-FIELD          PIC X(8).
           05  WS-X-SRC            PIC X(30).
           05  WS-X-TGT            PIC X(30).
           05  FILLER              PIC X(6) VALUE SPACES.

       01  WS-CTL.
           05  WS-C-TAG            PIC X(8).
           05  WS-C-SRC-READ       PIC 9(10).
           05  WS-C-SRC-UNIQUE     PIC 9(10).
           05  WS-C-DUP-SAME       PIC 9(10).
           05  WS-C-DUP-CONF       PIC 9(10).
           05  WS-C-TGT-CNT        PIC 9(10).
           05  WS-C-MATCHED        PIC 9(10).
           05  WS-C-MISMATCH       PIC 9(10).
           05  WS-C-MISSING        PIC 9(10).
           05  WS-C-EXTRA          PIC 9(10).
           05  WS-C-SRC-SIGN       PIC X(1).
           05  WS-C-SRC-TOT        PIC 9(13)V99.
           05  WS-C-TGT-SIGN       PIC X(1).
           05  WS-C-TGT-TOT        PIC 9(13)V99.
           05  WS-C-REASON         PIC X(20).

       PROCEDURE DIVISION.
       0000-MAIN.
           OPEN INPUT  SRC-FILE TGT-FILE
                OUTPUT DEDUP-FILE EXC-FILE CTL-FILE.
           PERFORM 2000-NEXT-SRC.
           PERFORM 2100-NEXT-TGT.
           PERFORM 3000-MERGE
               UNTIL WS-ABORT = 'Y'
                  OR (WS-SRC-KEY = HIGH-VALUES
                      AND WS-TGT-KEY = HIGH-VALUES).
           PERFORM 8000-WRITE-CTL.
           CLOSE SRC-FILE TGT-FILE DEDUP-FILE EXC-FILE CTL-FILE.
           PERFORM 8500-DISPLAY.
           IF WS-ABORT = 'Y'
               MOVE 12 TO RETURN-CODE
           ELSE
               MOVE 0 TO RETURN-CODE.
           STOP RUN.

      * ---- source: read until a new key (drops duplicates) ---------
       2000-NEXT-SRC.
           MOVE 'Y' TO WS-SKIP.
           PERFORM 2010-READ-ONE-SRC UNTIL WS-SKIP = 'N'.

       2010-READ-ONE-SRC.
           READ SRC-FILE AT END MOVE 'Y' TO WS-SRC-EOF.
           IF WS-SRC-EOF = 'Y'
               MOVE HIGH-VALUES TO WS-SRC-KEY
               MOVE 'N' TO WS-SKIP
           ELSE
               ADD 1 TO WS-SRC-READ
               PERFORM 2020-CLASSIFY-SRC.

       2020-CLASSIFY-SRC.
           IF SRC-KEY = WS-PREV-SRC-KEY
               PERFORM 2030-DUPLICATE
           ELSE
               IF SRC-KEY < WS-PREV-SRC-KEY
                   MOVE 'SRC SEQUENCE ERROR' TO WS-NEW-REASON
                   PERFORM 9900-ABORT
                   MOVE HIGH-VALUES TO WS-SRC-KEY
                   MOVE 'N' TO WS-SKIP
               ELSE
                   PERFORM 2040-ACCEPT-SRC.

       2030-DUPLICATE.
           IF SRC-REC = WS-KEPT-REC
               ADD 1 TO WS-DUP-SAME
           ELSE
               ADD 1 TO WS-DUP-CONF
               PERFORM 2035-DUPKEY-EXC.

       2035-DUPKEY-EXC.
           MOVE SRC-CUST-ID TO WS-X-CUST.
           MOVE SRC-ACCT-NO TO WS-X-ACCT.
           MOVE 'DUPKEY'    TO WS-X-TYPE.
           MOVE '*RECORD'   TO WS-X-FIELD.
           MOVE WS-K-NAME   TO WS-V-NAME.
           IF WS-K-BAL NUMERIC
               MOVE WS-K-BAL TO WS-V-BAL
           ELSE
               MOVE WS-K-BAL-X TO WS-VR-BAL.
           MOVE WS-VAL-GRP  TO WS-X-SRC.
           MOVE SRC-NAME    TO WS-V-NAME.
           IF SRC-BAL NUMERIC
               MOVE SRC-BAL TO WS-V-BAL
           ELSE
               MOVE SRC-BAL-X TO WS-VR-BAL.
           MOVE WS-VAL-GRP  TO WS-X-TGT.
           PERFORM 6000-WRITE-EXC.

       2040-ACCEPT-SRC.
           MOVE SRC-KEY TO WS-SRC-KEY.
           MOVE SRC-KEY TO WS-PREV-SRC-KEY.
           MOVE SRC-REC TO WS-KEPT-REC.
           ADD 1 TO WS-SRC-UNIQUE.
           IF SRC-BAL NUMERIC
               ADD SRC-BAL TO WS-SRC-TOT.
           WRITE DEDUP-REC FROM SRC-REC.
           MOVE 'N' TO WS-SKIP.

      * ---- target: one record, checked and normalised --------------
       2100-NEXT-TGT.
           READ TGT-FILE AT END MOVE 'Y' TO WS-TGT-EOF.
           IF WS-TGT-EOF = 'Y'
               MOVE HIGH-VALUES TO WS-TGT-KEY
           ELSE
               ADD 1 TO WS-TGT-CNT
               PERFORM 2110-CHECK-TGT.

       2110-CHECK-TGT.
           MOVE TGT-KEY TO WS-TGT-KEY.
           IF WS-TGT-KEY = WS-PREV-TGT-KEY
               MOVE 'TGT DUPLICATE KEY' TO WS-NEW-REASON
               PERFORM 9900-ABORT
           ELSE
               IF WS-TGT-KEY < WS-PREV-TGT-KEY
                   MOVE 'TGT SEQUENCE ERROR' TO WS-NEW-REASON
                   PERFORM 9900-ABORT
               ELSE
                   MOVE WS-TGT-KEY TO WS-PREV-TGT-KEY.
           PERFORM 2120-NORMALISE-TGT.

       2120-NORMALISE-TGT.
           MOVE 'N' TO WS-TBAL-OK.
           MOVE ZERO TO WS-TBAL-NUM.
           IF TGT-BAL-INT NUMERIC AND TGT-BAL-DEC NUMERIC
                                  AND TGT-BAL-DOT = '.'
               MOVE TGT-BAL-INT TO WS-TBAL-INT
               MOVE TGT-BAL-DEC TO WS-TBAL-DEC
               MOVE 'Y' TO WS-TBAL-OK
               ADD WS-TBAL-NUM TO WS-TGT-TOT.
           MOVE 'N' TO WS-TDATE-OK.
           MOVE SPACES TO WS-TDATE-N.
           IF TGT-D-SEP1 = '-' AND TGT-D-SEP2 = '-'
               MOVE TGT-D-YYYY TO WS-TD-YYYY
               MOVE TGT-D-MM   TO WS-TD-MM
               MOVE TGT-D-DD   TO WS-TD-DD
               MOVE 'Y' TO WS-TDATE-OK.

      * ---- the match-merge itself ---------------------------------
       3000-MERGE.
           IF WS-SRC-KEY < WS-TGT-KEY
               PERFORM 4000-MISSING
               PERFORM 2000-NEXT-SRC
           ELSE
               IF WS-SRC-KEY > WS-TGT-KEY
                   PERFORM 4100-EXTRA
                   PERFORM 2100-NEXT-TGT
               ELSE
                   PERFORM 5000-COMPARE
                   PERFORM 2000-NEXT-SRC
                   PERFORM 2100-NEXT-TGT.

       4000-MISSING.
           ADD 1 TO WS-MISSING.
           MOVE WS-K-CUST TO WS-X-CUST.
           MOVE WS-K-ACCT TO WS-X-ACCT.
           MOVE 'MISSING' TO WS-X-TYPE.
           MOVE '*RECORD' TO WS-X-FIELD.
           MOVE WS-K-NAME TO WS-V-NAME.
           IF WS-K-BAL NUMERIC
               MOVE WS-K-BAL TO WS-V-BAL
           ELSE
               MOVE WS-K-BAL-X TO WS-VR-BAL.
           MOVE WS-VAL-GRP TO WS-X-SRC.
           MOVE SPACES TO WS-X-TGT.
           PERFORM 6000-WRITE-EXC.

       4100-EXTRA.
           ADD 1 TO WS-EXTRA.
           MOVE TGT-CUST-ID TO WS-X-CUST.
           MOVE TGT-ACCT-NO TO WS-X-ACCT.
           MOVE 'EXTRA'   TO WS-X-TYPE.
           MOVE '*RECORD' TO WS-X-FIELD.
           MOVE SPACES TO WS-X-SRC.
           MOVE TGT-NAME TO WS-V-NAME.
           IF WS-TBAL-OK = 'Y'
               MOVE WS-TBAL-NUM TO WS-V-BAL
           ELSE
               MOVE TGT-BAL-TXT TO WS-VR-BAL.
           MOVE WS-VAL-GRP TO WS-X-TGT.
           PERFORM 6000-WRITE-EXC.

       5000-COMPARE.
           MOVE 'N' TO WS-DIFF.
           MOVE WS-K-CUST TO WS-X-CUST.
           MOVE WS-K-ACCT TO WS-X-ACCT.
           MOVE 'MISMATCH' TO WS-X-TYPE.
           IF WS-K-NAME NOT = TGT-NAME
               PERFORM 5100-NAME-DIFF.
           IF WS-K-BAL NOT NUMERIC OR WS-TBAL-OK = 'N'
               PERFORM 5200-BAL-RAW-DIFF
           ELSE
               IF WS-K-BAL NOT = WS-TBAL-NUM
                   PERFORM 5210-BAL-DIFF.
           IF WS-TDATE-OK = 'N'
               PERFORM 5300-DATE-DIFF
           ELSE
               IF WS-K-DATE NOT = WS-TDATE-N
                   PERFORM 5300-DATE-DIFF.
           IF WS-K-STATUS NOT = TGT-STATUS
               PERFORM 5400-STATUS-DIFF.
           IF WS-DIFF = 'Y'
               ADD 1 TO WS-MISMATCH
           ELSE
               ADD 1 TO WS-MATCHED.

       5100-NAME-DIFF.
           MOVE 'NAME' TO WS-X-FIELD.
           MOVE WS-K-NAME TO WS-X-SRC.
           MOVE TGT-NAME TO WS-X-TGT.
           PERFORM 5900-FLAG.

       5200-BAL-RAW-DIFF.
           MOVE 'BALANCE' TO WS-X-FIELD.
           MOVE WS-K-BAL-X TO WS-X-SRC.
           MOVE TGT-BAL-TXT TO WS-X-TGT.
           PERFORM 5900-FLAG.

       5210-BAL-DIFF.
           MOVE 'BALANCE' TO WS-X-FIELD.
           MOVE WS-K-BAL TO WS-EDIT-BAL.
           MOVE WS-EDIT-BAL TO WS-X-SRC.
           MOVE WS-TBAL-NUM TO WS-EDIT-BAL.
           MOVE WS-EDIT-BAL TO WS-X-TGT.
           PERFORM 5900-FLAG.

       5300-DATE-DIFF.
           MOVE 'TXNDATE' TO WS-X-FIELD.
           MOVE WS-K-DATE TO WS-X-SRC.
           MOVE TGT-DATE-TXT TO WS-X-TGT.
           PERFORM 5900-FLAG.

       5400-STATUS-DIFF.
           MOVE 'STATUS' TO WS-X-FIELD.
           MOVE WS-K-STATUS TO WS-X-SRC.
           MOVE TGT-STATUS TO WS-X-TGT.
           PERFORM 5900-FLAG.

       5900-FLAG.
           MOVE 'Y' TO WS-DIFF.
           PERFORM 6000-WRITE-EXC.

       6000-WRITE-EXC.
           WRITE EXC-REC FROM WS-EXC.
           ADD 1 TO WS-EXC-ROWS.

       8000-WRITE-CTL.
           IF WS-ABORT = 'Y'
               MOVE 'MIGABORT' TO WS-C-TAG
           ELSE
               MOVE 'MIGCTRL ' TO WS-C-TAG.
           MOVE WS-SRC-READ   TO WS-C-SRC-READ.
           MOVE WS-SRC-UNIQUE TO WS-C-SRC-UNIQUE.
           MOVE WS-DUP-SAME   TO WS-C-DUP-SAME.
           MOVE WS-DUP-CONF   TO WS-C-DUP-CONF.
           MOVE WS-TGT-CNT    TO WS-C-TGT-CNT.
           MOVE WS-MATCHED    TO WS-C-MATCHED.
           MOVE WS-MISMATCH   TO WS-C-MISMATCH.
           MOVE WS-MISSING    TO WS-C-MISSING.
           MOVE WS-EXTRA      TO WS-C-EXTRA.
           IF WS-SRC-TOT < ZERO
               MOVE '-' TO WS-C-SRC-SIGN
           ELSE
               MOVE '+' TO WS-C-SRC-SIGN.
           MOVE WS-SRC-TOT    TO WS-C-SRC-TOT.
           IF WS-TGT-TOT < ZERO
               MOVE '-' TO WS-C-TGT-SIGN
           ELSE
               MOVE '+' TO WS-C-TGT-SIGN.
           MOVE WS-TGT-TOT    TO WS-C-TGT-TOT.
           MOVE WS-REASON     TO WS-C-REASON.
           WRITE CTL-REC FROM WS-CTL.

       8500-DISPLAY.
           DISPLAY 'MIGMATCH SUMMARY'.
           DISPLAY '  SOURCE RECORDS READ : ' WS-SRC-READ.
           DISPLAY '  UNIQUE SOURCE       : ' WS-SRC-UNIQUE.
           DISPLAY '  IDENTICAL DUPLICATES: ' WS-DUP-SAME.
           DISPLAY '  CONFLICTING DUPS    : ' WS-DUP-CONF.
           DISPLAY '  TARGET RECORDS      : ' WS-TGT-CNT.
           DISPLAY '  MATCHED             : ' WS-MATCHED.
           DISPLAY '  MISMATCHED RECORDS  : ' WS-MISMATCH.
           DISPLAY '  MISSING IN TARGET   : ' WS-MISSING.
           DISPLAY '  EXTRA IN TARGET     : ' WS-EXTRA.
           DISPLAY '  EXCEPTION ROWS      : ' WS-EXC-ROWS.
           IF WS-ABORT = 'Y'
               DISPLAY '  *** ABORTED: ' WS-REASON.

      * keep only the FIRST abort reason
       9900-ABORT.
           IF WS-ABORT = 'N'
               MOVE 'Y' TO WS-ABORT
               MOVE WS-NEW-REASON TO WS-REASON.
