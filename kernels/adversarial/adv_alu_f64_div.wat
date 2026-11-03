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

  (func (export "run") (param $reps i32) (result i64)
    (local $k i32) (local $x i64) (local $y i64) (local $f f64)
    (local.set $x (i64.const 0x123456789abcdef))
    (local.set $y (i64.const 7))
    (local.set $f (f64.const 12345.678))
    (loop $rep
      (local.set $k (i32.const 65536))
      (loop $op
        (local.set $f (f64.div (local.get $f) (f64.const 1.0000001)))
        (br_if $op (local.tee $k (i32.sub (local.get $k) (i32.const 1)))))
      (br_if $rep (local.tee $reps (i32.sub (local.get $reps) (i32.const 1)))))
    (global.set $acc (i64.add (local.get $x) (i64.reinterpret_f64 (local.get $f))))
    (global.get $acc))
  (func (export "check") (result i64) (global.get $acc))
)
