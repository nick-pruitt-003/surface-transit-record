# Making a slow Python loop 40x faster with a small C function

This is the pattern used in `scripts/csa.c` and `scripts/time_router.py` to speed up the
timetable router. It is reusable anywhere a Python program spends most of its time in one
tight loop over arrays of numbers.

Result in this project: one route evaluation went from 0.46 s to 0.011 s, with identical answers.

## When this is the right tool

Use it when all of these are true:

- A profiler shows one function eating most of the run time.
- That function is a loop over numbers: array indexes, comparisons, additions.
- The loop cannot be expressed as whole-array numpy operations, because each step depends on
  the result of the previous one. A scan that updates a "best so far" table is the classic case.
- You call it thousands of times, so the saving multiplies.

Do not use it when:

- The slow part is I/O, a database, or a network call. C will not help.
- numpy vectorization already fits. Try that first, it is less code.
- The loop works on strings, dicts or objects rather than numbers.
- `numba` supports your Python version. Then `@njit` on the function is even less work.
  It did not support Python 3.14 when this was written, which is why this project uses plain C.

## Step 1: profile before touching anything

Guessing is unreliable. In this project the guess was "parsing the feed files is slow".
Measuring showed feed loading took 3 seconds. The real costs were a list comprehension that
rescanned 300,000 rows for every leg of an itinerary, and a cleanup pass that called the full
router about 700 times.

```python
import cProfile, pstats, io
pr = cProfile.Profile(); pr.enable()
slow_function(args)
pr.disable()
s = io.StringIO(); pstats.Stats(pr, stream=s).sort_stats('cumtime').print_stats(8)
print(s.getvalue())
```

Read the `cumtime` column. Optimize the top line and nothing else.

## Step 2: flatten the data into numpy arrays once

C cannot read Python lists of tuples or dicts. Convert them one time, at setup, into flat
arrays with fixed types. Typical conversions:

| Python structure | Flat form |
|---|---|
| list of records | one array per field: `dep[]`, `arr[]`, `from[]`, `to[]` |
| dict keyed by tuple or string | assign each key an integer id, store ids in an `int32` array |
| dict of lists, such as neighbors per node | CSR layout: `ptr[n+1]`, `to[]`, `weight[]`, where node `i` owns `to[ptr[i]:ptr[i+1]]` |
| set membership test | `uint8` mask array indexed by id |

```python
self.dep = np.ascontiguousarray(dep_list, dtype=np.float64)
self.trip = np.ascontiguousarray(trip_ids, dtype=np.int32)
```

`ascontiguousarray` with an explicit `dtype` matters. C reads raw memory, so a wrong type or a
strided view gives garbage, not an error.

## Step 3: write the loop in C

Keep the C function dumb. It takes pointers and sizes, reads input arrays, writes output arrays
the caller allocated, and returns a status code. No Python API, no globals, no file access.

```c
/* build: cc -O3 -shared -fPIC fast.c -o fast.so */
#include <stdlib.h>
#include <math.h>

int scan(int n, const double *dep, const double *arr, const int *from, const int *to,
         double *best /* in/out, size n_nodes */, int n_nodes)
{
    for (int k = 0; k < n; k++) {
        if (isinf(best[from[k]]) || best[from[k]] > dep[k]) continue;
        if (arr[k] < best[to[k]]) best[to[k]] = arr[k];
    }
    return 0;   /* return non-zero on malloc failure so the caller can raise */
}
```

Rules that avoid most bugs:

- The caller allocates every output array. C only fills them in.
- Pass every length explicitly. C does not know how long an array is.
- If the function needs scratch memory, `malloc` it, check for `NULL`, `free` it before every return.
- Mirror the Python logic line for line on the first pass. Make it clever later, if ever.

## Step 4: call it with ctypes

`ctypes` is in the standard library, so there is nothing to install and no build system.

```python
import ctypes, os, subprocess, numpy as np

here = os.path.dirname(os.path.abspath(__file__))
so, src = os.path.join(here, 'fast.so'), os.path.join(here, 'fast.c')
if not os.path.exists(so) or os.path.getmtime(so) < os.path.getmtime(src):
    subprocess.run(['cc', '-O3', '-shared', '-fPIC', src, '-o', so], check=True)
lib = ctypes.CDLL(so)

D = ctypes.POINTER(ctypes.c_double); I = ctypes.POINTER(ctypes.c_int)
lib.scan.argtypes = [ctypes.c_int, D, D, I, I, D, ctypes.c_int]
lib.scan.restype = ctypes.c_int

best = np.full(n_nodes, np.inf)
rc = lib.scan(len(dep), dep.ctypes.data_as(D), arr.ctypes.data_as(D),
              frm.ctypes.data_as(I), to.ctypes.data_as(I),
              best.ctypes.data_as(D), n_nodes)
if rc != 0: raise MemoryError('scan failed')
```

Details that matter:

- Always set `argtypes` and `restype`. Without them ctypes guesses, and guesses wrong for doubles.
- Rebuild automatically when the `.c` file is newer than the `.so`. Add the `.so` to `.gitignore`.
- Keep a reference to every numpy array for as long as C might use its pointer.
- Check the return code. A silent failure looks like a legitimate "no result".

## Step 5: keep the Python version and prove they agree

Do not delete the slow function. Keep it as the reference and as the fallback when no compiler
is available.

```python
def finish(self, *args):
    if self._fast is not None: return self._finish_fast(*args)
    return self._finish_py(*args)
```

Then test on real inputs, including shuffled and edge cases, before trusting the fast path:

```python
for case in cases:
    assert slow(case) == fast(case)
```

In this project the totals and the set of states covered matched on every case. The exact
itinerary sometimes differed where two options tied on arrival time, which is fine, but you only
know that is the explanation if you check what differs.

## Step 6: look again at what calls it

Once the inner loop is fast, the next bottleneck is usually the code around it. Here the search
also gained from caching results for a shared prefix of the input, so only the changed tail was
recomputed. Reprofile after each change and stop when the top line is no longer worth the effort.

## Pitfalls seen in practice

- **Wrong dtype.** Python ints become `int64` by default. C `int` is 32 bits. Cast explicitly.
- **Non-contiguous arrays.** Slices like `a[::2]` are views with strides. Use `np.ascontiguousarray`.
- **Hidden Python inside the loop.** Converting dicts to arrays on every call can cost more than
  the C call saves. Convert once, or keep state in array form between calls.
- **Multiprocessing.** With the `fork` start method, workers inherit the loaded library and the
  arrays for free. With `spawn`, each worker must load and build them itself.
- **Portability.** `cc` exists on macOS with the Xcode command line tools and on most Linux
  machines. On Windows this needs a different build command.

## Checklist

1. Profile. Identify the single hottest function.
2. Confirm it is a numeric loop that numpy cannot vectorize.
3. Flatten its inputs into typed, contiguous numpy arrays at setup time.
4. Write the loop in C, mirroring the Python logic.
5. Load it with ctypes, with `argtypes`, `restype`, auto-rebuild and a return-code check.
6. Keep the Python version. Assert both give the same results on real data.
7. Reprofile and decide whether the next bottleneck is worth it.
