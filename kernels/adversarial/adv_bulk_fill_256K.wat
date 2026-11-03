(module
  (memory (export "memory") 9)
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
      (local.set $k (i32.const 64))
      (loop $op
        (memory.fill (i32.const 0) (i32.wrap_i64 (local.get $a)) (i32.const 262144))
        (local.set $a (i64.add (local.get $a) (i64.load (i32.const 8))))
        (br_if $op (local.tee $k (i32.sub (local.get $k) (i32.const 1)))))
      (br_if $rep (local.tee $reps (i32.sub (local.get $reps) (i32.const 1)))))
    (global.set $acc (local.get $a))
    (global.get $acc))
  (func (export "check") (result i64) (global.get $acc))
)
