(module
  (memory (export "memory") 1)
  (global $seed (mut i32) (i32.const 2463534242))
  (global $ready (mut i32) (i32.const 0))
  (global $acc (mut i64) (i64.const 0))

  (func $rand (result i32)
    (global.set $seed (i32.xor (global.get $seed) (i32.shl (global.get $seed) (i32.const 13))))
    (global.set $seed (i32.xor (global.get $seed) (i32.shr_u (global.get $seed) (i32.const 17))))
    (global.set $seed (i32.xor (global.get $seed) (i32.shl (global.get $seed) (i32.const 5))))
    (global.get $seed))

  (func (export "run") (param $reps i32) (result i64) (local $k i32) (local $a i64)
    (loop $rep
      (local.set $k (i32.const 65536))
      (loop $op
        (if (i32.and (call $rand) (i32.const 1))
          (then (local.set $a (i64.add (local.get $a) (i64.const 3))))
          (else (local.set $a (i64.sub (local.get $a) (i64.const 1)))))
        (br_if $op (local.tee $k (i32.sub (local.get $k) (i32.const 1)))))
      (br_if $rep (local.tee $reps (i32.sub (local.get $reps) (i32.const 1)))))
    (global.set $acc (local.get $a))
    (global.get $acc))
  (func (export "check") (result i64) (global.get $acc))
)
