;; The sum of the integers from 0 to n, with named segments for the manual (spec 8.10).
(define (sum-to n)
  (let loop (#|@i-init|# (i 0) #|@end|#
             (acc 0))
    #|@body|#
    (if (> i n)
        acc
        (loop (+ i 1) (+ acc i)))
    #|@end|#))
