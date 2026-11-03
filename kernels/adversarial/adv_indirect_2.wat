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

  (type $unary (func (param i64) (result i64)))
  (table 2 funcref)
  (elem (i32.const 0) $t0 $t1)
  (func $t0 (param i64) (result i64) (i64.add (local.get 0) (i64.const 1)))
  (func $t1 (param i64) (result i64) (i64.add (local.get 0) (i64.const 2)))
  (func (export "run") (param $reps i32) (result i64) (local $k i32) (local $a i64)
    (loop $rep
      (local.set $k (i32.const 65536))
      (loop $op
        (local.set $a (call_indirect (type $unary) (local.get $a)
                        (i32.and (call $rand) (i32.const 1))))
        (br_if $op (local.tee $k (i32.sub (local.get $k) (i32.const 1)))))
      (br_if $rep (local.tee $reps (i32.sub (local.get $reps) (i32.const 1)))))
    (global.set $acc (local.get $a))
    (global.get $acc))
  (func (export "check") (result i64) (global.get $acc))
)
