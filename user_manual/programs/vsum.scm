;; A vector summed (the manual's "Columns that make room"), with named segments.
(define (vsum v)
  (let loop ((i 0) (s 0))
    (if (< i (vector-length v))
        (loop #|@next|#(+ i 1)#|@end|#
              (+ s #|@ref|#(vector-ref v i)#|@end|#))
        s)))
