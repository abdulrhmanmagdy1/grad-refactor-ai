# Blinded refactoring review packet

This packet compares alternative refactorings of the same input. Every candidate is shown without its producing system; labels are randomised per case.

Rate every candidate on three 1-5 scales (5 = best). Rate what you see, not what you
guess produced it:

- `correctness_1_5`    - confidence that the refactored code preserves the original behaviour;
- `readability_1_5`    - naming, structure, and clarity of the result;
- `maintainability_1_5` - how easily the result could be extended or debugged later.

Record one row per (case, candidate, rater) in `score_sheet.csv`, replacing the blank `rater`
column with your name or handle. Leave no score blank. Do not edit `packet.md` and do not open
`review_key.csv`: candidate labels are randomised per case and the key would break the blind
protocol.

## `async-function-clean-test-01`

Refactoring type: `async-function`

### Original code

```python
async def process_async_function_25(item):
    return item


async def _handle_batch_async_function_25_first(items):
    total = await process_async_function_25(items[0]) * 1
    total += await process_async_function_25(items[0]) * 2
    total += await process_async_function_25(items[0]) * 3
    total += await process_async_function_25(items[0]) * 4
    total += await process_async_function_25(items[0]) * 5
    total += await process_async_function_25(items[0]) * 6
    total += await process_async_function_25(items[0]) * 7
    total += await process_async_function_25(items[0]) * 8
    total += await process_async_function_25(items[0]) * 9
    total += await process_async_function_25(items[0]) * 10
    total += await process_async_function_25(items[0]) * 11
    total += await process_async_function_25(items[0]) * 12
    total += await process_async_function_25(items[0]) * 13
    total += await process_async_function_25(items[0]) * 14
    total += await process_async_function_25(items[0]) * 15
    total += await process_async_function_25(items[0]) * 16
    return total


async def _handle_batch_async_function_25_second(items):
    total = 0
    total += await process_async_function_25(items[0]) * 17
    total += await process_async_function_25(items[0]) * 18
    total += await process_async_function_25(items[0]) * 19
    total += await process_async_function_25(items[0]) * 20
    total += await process_async_function_25(items[0]) * 21
    total += await process_async_function_25(items[0]) * 22
    total += await process_async_function_25(items[0]) * 23
    total += await process_async_function_25(items[0]) * 24
    total += await process_async_function_25(items[0]) * 25
    total += await process_async_function_25(items[0]) * 26
    total += await process_async_function_25(items[0]) * 27
    total += await process_async_function_25(items[0]) * 28
    total += await process_async_function_25(items[0]) * 29
    total += await process_async_function_25(items[0]) * 30
    total += await process_async_function_25(items[0]) * 31
    return total


async def handle_batch_async_function_25(items):
    """Split the sequential awaits into two cohesive helpers (order preserved)."""
    return await _handle_batch_async_function_25_first(items) + await _handle_batch_async_function_25_second(items)
```

### Candidate 1

```python
async def process_async_function_25(item):
    return item

async def _handle_batch_async_function_25(items):
    return sum(await process_async_function_25(item) * i for i in range(1, 32))

async def handle_batch_async_function_25(items):
    return await _handle_batch_async_function_25(items)
```

### Candidate 2

```python
async def process_async_function_25(item):
    return item

def sum_multiples_of_n(number, n):
    total = 0
    for i in range(1, n+1):
        total += number * i
    return total

async def _handle_batch_async_function_25_first(items):
    return sum_multiples_of_n(await process_async_function_25(items[0]), 12)

async def _handle_batch_async_function_25_second(items):
    return sum_multiples_of_n(await process_async_function_25(items[0]), 12)

async def handle_batch_async_function_25(items):
    """Split the sequential awaits into two cohesive helpers (order preserved)."""
    return await _handle_batch_async_function_25_first(items) + await _handle_batch_async_function_25_second(items)
```

### Candidate 3

```python
async def process_async_function_25(item):
    return item


async def _handle_batch_async_function_25_first(items):
    total = await process_async_function_25(items[0]) * 1
    total += await process_async_function_25(items[0]) * 2
    total += await process_async_function_25(items[0]) * 3
    total += await process_async_function_25(items[0]) * 4
    total += await process_async_function_25(items[0]) * 5
    total += await process_async_function_25(items[0]) * 6
    total += await process_async_function_25(items[0]) * 7
    total += await process_async_function_25(items[0]) * 8
    total += await process_async_function_25(items[0]) * 9
    total += await process_async_function_25(items[0]) * 10
    total += await process_async_function_25(items[0]) * 11
    total += await process_async_function_25(items[0]) * 12
    total += await process_async_function_25(items[0]) * 13
    total += await process_async_function_25(items[0]) * 14
    total += await process_async_function_25(items[0]) * 15
    total += await process_async_function_25(items[0]) * 16
    return total


async def _handle_batch_async_function_25_second(items):
    total = 0
    total += await process_async_function_25(items[0]) * 17
    total += await process_async_function_25(items[0]) * 18
    total += await process_async_function_25(items[0]) * 19
    total += await process_async_function_25(items[0]) * 20
    total += await process_async_function_25(items[0]) * 21
    total += await process_async_function_25(items[0]) * 22
    total += await process_async_function_25(items[0]) * 23
    total += await process_async_function_25(items[0]) * 24
    total += await process_async_function_25(items[0]) * 25
    total += await process_async_function_25(items[0]) * 26
    total += await process_async_function_25(items[0]) * 27
    total += await process_async_function_25(items[0]) * 28
    total += await process_async_function_25(items[0]) * 29
    total += await process_async_function_25(items[0]) * 30
    total += await process_async_function_25(items[0]) * 31
    return total


async def handle_batch_async_function_25(items):
    """Split the sequential awaits into two cohesive helpers (order preserved)."""
    return await _handle_batch_async_function_25_first(items) + await _handle_batch_async_function_25_second(items)
```

### Candidate 4

```python
async def process_async_function_25(item):
    return item


async def _handle_batch_async_function_25_first(items):
    total = await process_async_function_25(items[0]) * 1
    total += await process_async_function_25(items[0]) * 2
    total += await process_async_function_25(items[0]) * 3
    total += await process_async_function_25(items[0]) * 4
    total += await process_async_function_25(items[0]) * 5
    total += await process_async_function_25(items[0]) * 6
    total += await process_async_function_25(items[0]) * 7
    total += await process_async_function_25(items[0]) * 8
    total += await process_async_function_25(items[0]) * 9
    total += await process_async_function_25(items[0]) * 10
    total += await process_async_function_25(items[0]) * 11
    total += await process_async_function_25(items[0]) * 12
    total += await process_async_function_25(items[0]) * 13
    total += await process_async_function_25(items[0]) * 14
    total += await process_async_function_25(items[0]) * 15
    total += await process_async_function_25(items[0]) * 16
    return total


async def _handle_batch_async_function_25_second(items):
    total = 0
    total += await process_async_function_25(items[0]) * 17
    total += await process_async_function_25(items[0]) * 18
    total += await process_async_function_25(items[0]) * 19
    total += await process_async_function_25(items[0]) * 20
    total += await process_async_function_25(items[0]) * 21
    total += await process_async_function_25(items[0]) * 22
    total += await process_async_function_25(items[0]) * 23
    total += await process_async_function_25(items[0]) * 24
    total += await process_async_function_25(items[0]) * 25
    total += await process_async_function_25(items[0]) * 26
    total += await process_async_function_25(items[0]) * 27
    total += await process_async_function_25(items[0]) * 28
    total += await process_async_function_25(items[0]) * 29
    total += await process_async_function_25(items[0]) * 30
    total += await process_async_function_25(items[0]) * 31
    return total


async def handle_batch_async_function_25(items):
    """Split the sequential awaits into two cohesive helpers (order preserved)."""
    return await _handle_batch_async_function_25_first(items) + await _handle_batch_async_function_25_second(items)
```

## `async-function-clean-test-02`

Refactoring type: `async-function`

### Original code

```python
async def transform_async_function_26(item):
    return item * 3


async def _handle_first_async_function_26(item):
    total = await transform_async_function_26(item)
    total = total + await transform_async_function_26(item) * 2
    total = total + await transform_async_function_26(item) * 3
    total = total + await transform_async_function_26(item) * 4
    total = total + await transform_async_function_26(item) * 5
    total = total + await transform_async_function_26(item) * 6
    total = total + await transform_async_function_26(item) * 7
    total = total + await transform_async_function_26(item) * 8
    total = total + await transform_async_function_26(item) * 9
    total = total + await transform_async_function_26(item) * 10
    total = total + await transform_async_function_26(item) * 11
    total = total + await transform_async_function_26(item) * 12
    total = total + await transform_async_function_26(item) * 13
    total = total + await transform_async_function_26(item) * 14
    total = total + await transform_async_function_26(item) * 15
    total = total + await transform_async_function_26(item) * 16
    return total


async def _handle_second_async_function_26(item):
    total = 0
    total = total + await transform_async_function_26(item) * 17
    total = total + await transform_async_function_26(item) * 18
    total = total + await transform_async_function_26(item) * 19
    total = total + await transform_async_function_26(item) * 20
    total = total + await transform_async_function_26(item) * 21
    total = total + await transform_async_function_26(item) * 22
    total = total + await transform_async_function_26(item) * 23
    total = total + await transform_async_function_26(item) * 24
    total = total + await transform_async_function_26(item) * 25
    total = total + await transform_async_function_26(item) * 26
    total = total + await transform_async_function_26(item) * 27
    total = total + await transform_async_function_26(item) * 28
    total = total + await transform_async_function_26(item) * 29
    total = total + await transform_async_function_26(item) * 30
    total = total + await transform_async_function_26(item) * 31
    total = total + await transform_async_function_26(item) * 32
    return total


async def handle_async_function_26(item):
    """Split the await sequence into two cohesive helpers (order preserved)."""
    return await _handle_first_async_function_26(item) + await _handle_second_async_function_26(item)
```

### Candidate 1

```python
async def transform_async_function_26(item):
    return item * 3


async def _handle_first_async_function_26(item):
    total = await transform_async_function_26(item)
    total = total + await transform_async_function_26(item) * 2
    total = total + await transform_async_function_26(item) * 3
    total = total + await transform_async_function_26(item) * 4
    total = total + await transform_async_function_26(item) * 5
    total = total + await transform_async_function_26(item) * 6
    total = total + await transform_async_function_26(item) * 7
    total = total + await transform_async_function_26(item) * 8
    total = total + await transform_async_function_26(item) * 9
    total = total + await transform_async_function_26(item) * 10
    total = total + await transform_async_function_26(item) * 11
    total = total + await transform_async_function_26(item) * 12
    total = total + await transform_async_function_26(item) * 13
    total = total + await transform_async_function_26(item) * 14
    total = total + await transform_async_function_26(item) * 15
    total = total + await transform_async_function_26(item) * 16
    return total


async def _handle_second_async_function_26(item):
    total = 0
    total = total + await transform_async_function_26(item) * 17
    total = total + await transform_async_function_26(item) * 18
    total = total + await transform_async_function_26(item) * 19
    total = total + await transform_async_function_26(item) * 20
    total = total + await transform_async_function_26(item) * 21
    total = total + await transform_async_function_26(item) * 22
    total = total + await transform_async_function_26(item) * 23
    total = total + await transform_async_function_26(item) * 24
    total = total + await transform_async_function_26(item) * 25
    total = total + await transform_async_function_26(item) * 26
    total = total + await transform_async_function_26(item) * 27
    total = total + await transform_async_function_26(item) * 28
    total = total + await transform_async_function_26(item) * 29
    total = total + await transform_async_function_26(item) * 30
    total = total + await transform_async_function_26(item) * 31
    total = total + await transform_async_function_26(item) * 32
    return total


async def handle_async_function_26(item):
    """Split the await sequence into two cohesive helpers (order preserved)."""
    return await _handle_first_async_function_26(item) + await _handle_second_async_function_26(item)
```

### Candidate 2

```python
async def transform_async_function_26(item):
    return item * 3


async def _handle_first_async_function_26(item):
    total = await transform_async_function_26(item)
    total = total + await transform_async_function_26(item) * 2
    total = total + await transform_async_function_26(item) * 3
    total = total + await transform_async_function_26(item) * 4
    total = total + await transform_async_function_26(item) * 5
    total = total + await transform_async_function_26(item) * 6
    total = total + await transform_async_function_26(item) * 7
    total = total + await transform_async_function_26(item) * 8
    total = total + await transform_async_function_26(item) * 9
    total = total + await transform_async_function_26(item) * 10
    total = total + await transform_async_function_26(item) * 11
    total = total + await transform_async_function_26(item) * 12
    total = total + await transform_async_function_26(item) * 13
    total = total + await transform_async_function_26(item) * 14
    total = total + await transform_async_function_26(item) * 15
    total = total + await transform_async_function_26(item) * 16
    return total


async def _handle_second_async_function_26(item):
    total = 0
    total = total + await transform_async_function_26(item) * 17
    total = total + await transform_async_function_26(item) * 18
    total = total + await transform_async_function_26(item) * 19
    total = total + await transform_async_function_26(item) * 20
    total = total + await transform_async_function_26(item) * 21
    total = total + await transform_async_function_26(item) * 22
    total = total + await transform_async_function_26(item) * 23
    total = total + await transform_async_function_26(item) * 24
    total = total + await transform_async_function_26(item) * 25
    total = total + await transform_async_function_26(item) * 26
    total = total + await transform_async_function_26(item) * 27
    total = total + await transform_async_function_26(item) * 28
    total = total + await transform_async_function_26(item) * 29
    total = total + await transform_async_function_26(item) * 30
    total = total + await transform_async_function_26(item) * 31
    total = total + await transform_async_function_26(item) * 32
    return total


async def handle_async_function_26(item):
    """Split the await sequence into two cohesive helpers (order preserved)."""
    return await _handle_first_async_function_26(item) + await _handle_second_async_function_26(item)
```

### Candidate 3

```python
async def transform_async_function_26(item):
    return item * 3


async def _handle_first_async_function_26(item):
    return sum(await transform_async_function_26(item) * i for i in range(1, 17))


async def _handle_second_async_function_26(item):
    return sum(await transform_async_function_26(item) * i for i in range(17, 33))


async def handle_async_function_26(item):
    """Split the await sequence into two cohesive helpers (order preserved)."""
    return await _handle_first_async_function_26(item) + await _handle_second_async_function_26(item)
```

### Candidate 4

```python
async def transform_async_function_26(item):
    return item * 3


async def _sum_transformed_items(items, multiplier):
    total = 0
    for item in items:
        total += transform_async_function_26(item) * multiplier
    return total


async def _handle_first_async_function_26(item):
    return await _sum_transformed_items([item] * 16, 1)


async def _handle_second_async_function_26(item):
    return await _sum_transformed_items([item] * 32, 2)


async def handle_async_function_26(item):
    """Split the await sequence into two cohesive helpers (order preserved)."""
    return await _handle_first_async_function_26(item) + await _handle_second_async_function_26(item)
```

## `async-function-test-01`

Refactoring type: `async-function`

### Original code

```python
async def process_async_function_25(item):
    return item


async def handle_batch_async_function_25(items):
    total_25 = await process_async_function_25(items[0]) * 1
    total_25 += await process_async_function_25(items[0]) * 2
    total_25 += await process_async_function_25(items[0]) * 3
    total_25 += await process_async_function_25(items[0]) * 4
    total_25 += await process_async_function_25(items[0]) * 5
    total_25 += await process_async_function_25(items[0]) * 6
    total_25 += await process_async_function_25(items[0]) * 7
    total_25 += await process_async_function_25(items[0]) * 8
    total_25 += await process_async_function_25(items[0]) * 9
    total_25 += await process_async_function_25(items[0]) * 10
    total_25 += await process_async_function_25(items[0]) * 11
    total_25 += await process_async_function_25(items[0]) * 12
    total_25 += await process_async_function_25(items[0]) * 13
    total_25 += await process_async_function_25(items[0]) * 14
    total_25 += await process_async_function_25(items[0]) * 15
    total_25 += await process_async_function_25(items[0]) * 16
    total_25 += await process_async_function_25(items[0]) * 17
    total_25 += await process_async_function_25(items[0]) * 18
    total_25 += await process_async_function_25(items[0]) * 19
    total_25 += await process_async_function_25(items[0]) * 20
    total_25 += await process_async_function_25(items[0]) * 21
    total_25 += await process_async_function_25(items[0]) * 22
    total_25 += await process_async_function_25(items[0]) * 23
    total_25 += await process_async_function_25(items[0]) * 24
    total_25 += await process_async_function_25(items[0]) * 25
    total_25 += await process_async_function_25(items[0]) * 26
    total_25 += await process_async_function_25(items[0]) * 27
    total_25 += await process_async_function_25(items[0]) * 28
    total_25 += await process_async_function_25(items[0]) * 29
    total_25 += await process_async_function_25(items[0]) * 30
    total_25 += await process_async_function_25(items[0]) * 31
    return total_25
```

### Candidate 1

```python
import asyncio

async def process_async_function_25(item):
    return item

async def calculate_total(items):
    return sum(await asyncio.gather(*(process_async_function_25(item) * i for i in range(1, 32))))

async def handle_batch_async_function_25(items):
    return await calculate_total(items)
```

### Candidate 2

```python
async def process_async_function_25(item):
    return item


async def handle_batch_async_function_25(items):
    total_25 = await process_async_function_25(items[0]) * 1
    total_25 += await process_async_function_25(items[0]) * 2
    total_25 += await process_async_function_25(items[0]) * 3
    total_25 += await process_async_function_25(items[0]) * 4
    total_25 += await process_async_function_25(items[0]) * 5
    total_25 += await process_async_function_25(items[0]) * 6
    total_25 += await process_async_function_25(items[0]) * 7
    total_25 += await process_async_function_25(items[0]) * 8
    total_25 += await process_async_function_25(items[0]) * 9
    total_25 += await process_async_function_25(items[0]) * 10
    total_25 += await process_async_function_25(items[0]) * 11
    total_25 += await process_async_function_25(items[0]) * 12
    total_25 += await process_async_function_25(items[0]) * 13
    total_25 += await process_async_function_25(items[0]) * 14
    total_25 += await process_async_function_25(items[0]) * 15
    total_25 += await process_async_function_25(items[0]) * 16
    total_25 += await process_async_function_25(items[0]) * 17
    total_25 += await process_async_function_25(items[0]) * 18
    total_25 += await process_async_function_25(items[0]) * 19
    total_25 += await process_async_function_25(items[0]) * 20
    total_25 += await process_async_function_25(items[0]) * 21
    total_25 += await process_async_function_25(items[0]) * 22
    total_25 += await process_async_function_25(items[0]) * 23
    total_25 += await process_async_function_25(items[0]) * 24
    total_25 += await process_async_function_25(items[0]) * 25
    total_25 += await process_async_function_25(items[0]) * 26
    total_25 += await process_async_function_25(items[0]) * 27
    total_25 += await process_async_function_25(items[0]) * 28
    total_25 += await process_async_function_25(items[0]) * 29
    total_25 += await process_async_function_25(items[0]) * 30
    total_25 += await process_async_function_25(items[0]) * 31
    return total_25
```

### Candidate 3

```python
async def process_async_function_25(item):
    return item


async def _handle_first_async_function_25(items):
    total = await process_async_function_25(items[0]) * 1
    total += await process_async_function_25(items[0]) * 2
    total += await process_async_function_25(items[0]) * 3
    total += await process_async_function_25(items[0]) * 4
    total += await process_async_function_25(items[0]) * 5
    total += await process_async_function_25(items[0]) * 6
    total += await process_async_function_25(items[0]) * 7
    total += await process_async_function_25(items[0]) * 8
    total += await process_async_function_25(items[0]) * 9
    total += await process_async_function_25(items[0]) * 10
    total += await process_async_function_25(items[0]) * 11
    total += await process_async_function_25(items[0]) * 12
    total += await process_async_function_25(items[0]) * 13
    total += await process_async_function_25(items[0]) * 14
    total += await process_async_function_25(items[0]) * 15
    total += await process_async_function_25(items[0]) * 16
    return total


async def _handle_second_async_function_25(items):
    total = 0
    total += await process_async_function_25(items[0]) * 17
    total += await process_async_function_25(items[0]) * 18
    total += await process_async_function_25(items[0]) * 19
    total += await process_async_function_25(items[0]) * 20
    total += await process_async_function_25(items[0]) * 21
    total += await process_async_function_25(items[0]) * 22
    total += await process_async_function_25(items[0]) * 23
    total += await process_async_function_25(items[0]) * 24
    total += await process_async_function_25(items[0]) * 25
    total += await process_async_function_25(items[0]) * 26
    total += await process_async_function_25(items[0]) * 27
    total += await process_async_function_25(items[0]) * 28
    total += await process_async_function_25(items[0]) * 29
    total += await process_async_function_25(items[0]) * 30
    total += await process_async_function_25(items[0]) * 31
    return total


async def handle_batch_async_function_25(items):
    """Split the sequential awaits into two cohesive helpers (order preserved)."""
    return await _handle_first_async_function_25(items) + await _handle_second_async_function_25(items)
```

### Candidate 4

```python
async def process_async_function_25(item):
    return item

def multiply_by_n(item, n):
    return item * n

async def handle_batch_async_function_25(items):
    total_25 = sum(multiply_by_n(items[0], n) for n in range(1, 32))
    return total_25
```

## `async-function-test-02`

Refactoring type: `async-function`

### Original code

```python
async def transform_async_function_26(item):
    return item * 3


async def handle_async_function_26(item):
    total = await transform_async_function_26(item)
    total = total + await transform_async_function_26(item) * 2
    total = total + await transform_async_function_26(item) * 3
    total = total + await transform_async_function_26(item) * 4
    total = total + await transform_async_function_26(item) * 5
    total = total + await transform_async_function_26(item) * 6
    total = total + await transform_async_function_26(item) * 7
    total = total + await transform_async_function_26(item) * 8
    total = total + await transform_async_function_26(item) * 9
    total = total + await transform_async_function_26(item) * 10
    total = total + await transform_async_function_26(item) * 11
    total = total + await transform_async_function_26(item) * 12
    total = total + await transform_async_function_26(item) * 13
    total = total + await transform_async_function_26(item) * 14
    total = total + await transform_async_function_26(item) * 15
    total = total + await transform_async_function_26(item) * 16
    total = total + await transform_async_function_26(item) * 17
    total = total + await transform_async_function_26(item) * 18
    total = total + await transform_async_function_26(item) * 19
    total = total + await transform_async_function_26(item) * 20
    total = total + await transform_async_function_26(item) * 21
    total = total + await transform_async_function_26(item) * 22
    total = total + await transform_async_function_26(item) * 23
    total = total + await transform_async_function_26(item) * 24
    total = total + await transform_async_function_26(item) * 25
    total = total + await transform_async_function_26(item) * 26
    total = total + await transform_async_function_26(item) * 27
    total = total + await transform_async_function_26(item) * 28
    total = total + await transform_async_function_26(item) * 29
    total = total + await transform_async_function_26(item) * 30
    total = total + await transform_async_function_26(item) * 31
    total = total + await transform_async_function_26(item) * 32
    return total
```

### Candidate 1

```python
async def transform_async_function_26(item):
    return item * 3


async def handle_async_function_26(item):
    total = await transform_async_function_26(item)
    total = total + await transform_async_function_26(item) * 2
    total = total + await transform_async_function_26(item) * 3
    total = total + await transform_async_function_26(item) * 4
    total = total + await transform_async_function_26(item) * 5
    total = total + await transform_async_function_26(item) * 6
    total = total + await transform_async_function_26(item) * 7
    total = total + await transform_async_function_26(item) * 8
    total = total + await transform_async_function_26(item) * 9
    total = total + await transform_async_function_26(item) * 10
    total = total + await transform_async_function_26(item) * 11
    total = total + await transform_async_function_26(item) * 12
    total = total + await transform_async_function_26(item) * 13
    total = total + await transform_async_function_26(item) * 14
    total = total + await transform_async_function_26(item) * 15
    total = total + await transform_async_function_26(item) * 16
    total = total + await transform_async_function_26(item) * 17
    total = total + await transform_async_function_26(item) * 18
    total = total + await transform_async_function_26(item) * 19
    total = total + await transform_async_function_26(item) * 20
    total = total + await transform_async_function_26(item) * 21
    total = total + await transform_async_function_26(item) * 22
    total = total + await transform_async_function_26(item) * 23
    total = total + await transform_async_function_26(item) * 24
    total = total + await transform_async_function_26(item) * 25
    total = total + await transform_async_function_26(item) * 26
    total = total + await transform_async_function_26(item) * 27
    total = total + await transform_async_function_26(item) * 28
    total = total + await transform_async_function_26(item) * 29
    total = total + await transform_async_function_26(item) * 30
    total = total + await transform_async_function_26(item) * 31
    total = total + await transform_async_function_26(item) * 32
    return total
```

### Candidate 2

```python
from typing import Any

async def transform_async_function_26(item: Any) -> Any:
    return item * 3


async def handle_async_function_26(item: Any) -> Any:
    total = await transform_async_function_26(item)
    multiplier = 1
    for _ in range(30):
        total += await transform_async_function_26(item) * multiplier
        multiplier += 1
    return total
```

### Candidate 3

```python
async def transform_async_function_26(item):
    return item * 3


async def _handle_first_async_function_26(item):
    total = await transform_async_function_26(item)
    total = total + await transform_async_function_26(item) * 2
    total = total + await transform_async_function_26(item) * 3
    total = total + await transform_async_function_26(item) * 4
    total = total + await transform_async_function_26(item) * 5
    total = total + await transform_async_function_26(item) * 6
    total = total + await transform_async_function_26(item) * 7
    total = total + await transform_async_function_26(item) * 8
    total = total + await transform_async_function_26(item) * 9
    total = total + await transform_async_function_26(item) * 10
    total = total + await transform_async_function_26(item) * 11
    total = total + await transform_async_function_26(item) * 12
    total = total + await transform_async_function_26(item) * 13
    total = total + await transform_async_function_26(item) * 14
    total = total + await transform_async_function_26(item) * 15
    total = total + await transform_async_function_26(item) * 16
    return total


async def _handle_second_async_function_26(item):
    total = 0
    total = total + await transform_async_function_26(item) * 17
    total = total + await transform_async_function_26(item) * 18
    total = total + await transform_async_function_26(item) * 19
    total = total + await transform_async_function_26(item) * 20
    total = total + await transform_async_function_26(item) * 21
    total = total + await transform_async_function_26(item) * 22
    total = total + await transform_async_function_26(item) * 23
    total = total + await transform_async_function_26(item) * 24
    total = total + await transform_async_function_26(item) * 25
    total = total + await transform_async_function_26(item) * 26
    total = total + await transform_async_function_26(item) * 27
    total = total + await transform_async_function_26(item) * 28
    total = total + await transform_async_function_26(item) * 29
    total = total + await transform_async_function_26(item) * 30
    total = total + await transform_async_function_26(item) * 31
    total = total + await transform_async_function_26(item) * 32
    return total


async def handle_async_function_26(item):
    """Split the two halves into cohesive helpers (order preserved)."""
    return await _handle_first_async_function_26(item) + await _handle_second_async_function_26(item)
```

### Candidate 4

```python
async def transform_async_function_26(item):
    return item * 3

async def handle_async_function_26(item):
    total = 0
    for _ in range(1, 32):
        total += await transform_async_function_26(item) * _
    return total
```

## `async-function-test-03`

Refactoring type: `async-function`

### Original code

```python
async def process_async_function_27(item):
    return item


async def handle_batch_async_function_27(items):
    total_27 = await process_async_function_27(items[0]) * 1
    total_27 += await process_async_function_27(items[0]) * 2
    total_27 += await process_async_function_27(items[0]) * 3
    total_27 += await process_async_function_27(items[0]) * 4
    total_27 += await process_async_function_27(items[0]) * 5
    total_27 += await process_async_function_27(items[0]) * 6
    total_27 += await process_async_function_27(items[0]) * 7
    total_27 += await process_async_function_27(items[0]) * 8
    total_27 += await process_async_function_27(items[0]) * 9
    total_27 += await process_async_function_27(items[0]) * 10
    total_27 += await process_async_function_27(items[0]) * 11
    total_27 += await process_async_function_27(items[0]) * 12
    total_27 += await process_async_function_27(items[0]) * 13
    total_27 += await process_async_function_27(items[0]) * 14
    total_27 += await process_async_function_27(items[0]) * 15
    total_27 += await process_async_function_27(items[0]) * 16
    total_27 += await process_async_function_27(items[0]) * 17
    total_27 += await process_async_function_27(items[0]) * 18
    total_27 += await process_async_function_27(items[0]) * 19
    total_27 += await process_async_function_27(items[0]) * 20
    total_27 += await process_async_function_27(items[0]) * 21
    total_27 += await process_async_function_27(items[0]) * 22
    total_27 += await process_async_function_27(items[0]) * 23
    total_27 += await process_async_function_27(items[0]) * 24
    total_27 += await process_async_function_27(items[0]) * 25
    total_27 += await process_async_function_27(items[0]) * 26
    total_27 += await process_async_function_27(items[0]) * 27
    total_27 += await process_async_function_27(items[0]) * 28
    total_27 += await process_async_function_27(items[0]) * 29
    total_27 += await process_async_function_27(items[0]) * 30
    total_27 += await process_async_function_27(items[0]) * 31
    return total_27
```

### Candidate 1

```python
import asyncio

async def process_async_function_27(item):
    return item

async def handle_batch_async_function_27(items):
    return sum(process_async_function_27(item) * i for i in range(1, 32))
```

### Candidate 2

```python
async def process_async_function_27(item):
    return item


async def handle_batch_async_function_27(items):
    total_27 = await process_async_function_27(items[0]) * 1
    total_27 += await process_async_function_27(items[0]) * 2
    total_27 += await process_async_function_27(items[0]) * 3
    total_27 += await process_async_function_27(items[0]) * 4
    total_27 += await process_async_function_27(items[0]) * 5
    total_27 += await process_async_function_27(items[0]) * 6
    total_27 += await process_async_function_27(items[0]) * 7
    total_27 += await process_async_function_27(items[0]) * 8
    total_27 += await process_async_function_27(items[0]) * 9
    total_27 += await process_async_function_27(items[0]) * 10
    total_27 += await process_async_function_27(items[0]) * 11
    total_27 += await process_async_function_27(items[0]) * 12
    total_27 += await process_async_function_27(items[0]) * 13
    total_27 += await process_async_function_27(items[0]) * 14
    total_27 += await process_async_function_27(items[0]) * 15
    total_27 += await process_async_function_27(items[0]) * 16
    total_27 += await process_async_function_27(items[0]) * 17
    total_27 += await process_async_function_27(items[0]) * 18
    total_27 += await process_async_function_27(items[0]) * 19
    total_27 += await process_async_function_27(items[0]) * 20
    total_27 += await process_async_function_27(items[0]) * 21
    total_27 += await process_async_function_27(items[0]) * 22
    total_27 += await process_async_function_27(items[0]) * 23
    total_27 += await process_async_function_27(items[0]) * 24
    total_27 += await process_async_function_27(items[0]) * 25
    total_27 += await process_async_function_27(items[0]) * 26
    total_27 += await process_async_function_27(items[0]) * 27
    total_27 += await process_async_function_27(items[0]) * 28
    total_27 += await process_async_function_27(items[0]) * 29
    total_27 += await process_async_function_27(items[0]) * 30
    total_27 += await process_async_function_27(items[0]) * 31
    return total_27
```

### Candidate 3

```python
async def process_async_function_27(item):
    return item

def calculate_total(items):
    return sum(process_async_function_27(item) * i for i in range(1, 32))

async def handle_batch_async_function_27(items):
    return await calculate_total(items)
```

### Candidate 4

```python
async def process_async_function_27(item):
    return item


async def _handle_batch_async_function_27_first(items):
    total = await process_async_function_27(items[0]) * 1
    total += await process_async_function_27(items[0]) * 2
    total += await process_async_function_27(items[0]) * 3
    total += await process_async_function_27(items[0]) * 4
    total += await process_async_function_27(items[0]) * 5
    total += await process_async_function_27(items[0]) * 6
    total += await process_async_function_27(items[0]) * 7
    total += await process_async_function_27(items[0]) * 8
    total += await process_async_function_27(items[0]) * 9
    total += await process_async_function_27(items[0]) * 10
    total += await process_async_function_27(items[0]) * 11
    total += await process_async_function_27(items[0]) * 12
    total += await process_async_function_27(items[0]) * 13
    total += await process_async_function_27(items[0]) * 14
    total += await process_async_function_27(items[0]) * 15
    total += await process_async_function_27(items[0]) * 16
    return total


async def _handle_batch_async_function_27_second(items):
    total = 0
    total += await process_async_function_27(items[0]) * 17
    total += await process_async_function_27(items[0]) * 18
    total += await process_async_function_27(items[0]) * 19
    total += await process_async_function_27(items[0]) * 20
    total += await process_async_function_27(items[0]) * 21
    total += await process_async_function_27(items[0]) * 22
    total += await process_async_function_27(items[0]) * 23
    total += await process_async_function_27(items[0]) * 24
    total += await process_async_function_27(items[0]) * 25
    total += await process_async_function_27(items[0]) * 26
    total += await process_async_function_27(items[0]) * 27
    total += await process_async_function_27(items[0]) * 28
    total += await process_async_function_27(items[0]) * 29
    total += await process_async_function_27(items[0]) * 30
    total += await process_async_function_27(items[0]) * 31
    return total


async def handle_batch_async_function_27(items):
    """Split the sequential awaits into two cohesive helpers (order preserved)."""
    return await _handle_batch_async_function_27_first(items) + await _handle_batch_async_function_27_second(items)
```

## `async-function-test-04`

Refactoring type: `async-function`

### Original code

```python
async def transform_async_function_28(item):
    return item * 3


async def handle_async_function_28(item):
    total = await transform_async_function_28(item)
    total = total + await transform_async_function_28(item) * 2
    total = total + await transform_async_function_28(item) * 3
    total = total + await transform_async_function_28(item) * 4
    total = total + await transform_async_function_28(item) * 5
    total = total + await transform_async_function_28(item) * 6
    total = total + await transform_async_function_28(item) * 7
    total = total + await transform_async_function_28(item) * 8
    total = total + await transform_async_function_28(item) * 9
    total = total + await transform_async_function_28(item) * 10
    total = total + await transform_async_function_28(item) * 11
    total = total + await transform_async_function_28(item) * 12
    total = total + await transform_async_function_28(item) * 13
    total = total + await transform_async_function_28(item) * 14
    total = total + await transform_async_function_28(item) * 15
    total = total + await transform_async_function_28(item) * 16
    total = total + await transform_async_function_28(item) * 17
    total = total + await transform_async_function_28(item) * 18
    total = total + await transform_async_function_28(item) * 19
    total = total + await transform_async_function_28(item) * 20
    total = total + await transform_async_function_28(item) * 21
    total = total + await transform_async_function_28(item) * 22
    total = total + await transform_async_function_28(item) * 23
    total = total + await transform_async_function_28(item) * 24
    total = total + await transform_async_function_28(item) * 25
    total = total + await transform_async_function_28(item) * 26
    total = total + await transform_async_function_28(item) * 27
    total = total + await transform_async_function_28(item) * 28
    total = total + await transform_async_function_28(item) * 29
    total = total + await transform_async_function_28(item) * 30
    total = total + await transform_async_function_28(item) * 31
    total = total + await transform_async_function_28(item) * 32
    return total
```

### Candidate 1

```python
async def transform_async_function_28(item):
    return item * 3


async def _handle_first_async_function_28(item):
    total = await transform_async_function_28(item)
    total = total + await transform_async_function_28(item) * 2
    total = total + await transform_async_function_28(item) * 3
    total = total + await transform_async_function_28(item) * 4
    total = total + await transform_async_function_28(item) * 5
    total = total + await transform_async_function_28(item) * 6
    total = total + await transform_async_function_28(item) * 7
    total = total + await transform_async_function_28(item) * 8
    total = total + await transform_async_function_28(item) * 9
    total = total + await transform_async_function_28(item) * 10
    total = total + await transform_async_function_28(item) * 11
    total = total + await transform_async_function_28(item) * 12
    total = total + await transform_async_function_28(item) * 13
    total = total + await transform_async_function_28(item) * 14
    total = total + await transform_async_function_28(item) * 15
    total = total + await transform_async_function_28(item) * 16
    return total


async def _handle_second_async_function_28(item):
    total = 0
    total = total + await transform_async_function_28(item) * 17
    total = total + await transform_async_function_28(item) * 18
    total = total + await transform_async_function_28(item) * 19
    total = total + await transform_async_function_28(item) * 20
    total = total + await transform_async_function_28(item) * 21
    total = total + await transform_async_function_28(item) * 22
    total = total + await transform_async_function_28(item) * 23
    total = total + await transform_async_function_28(item) * 24
    total = total + await transform_async_function_28(item) * 25
    total = total + await transform_async_function_28(item) * 26
    total = total + await transform_async_function_28(item) * 27
    total = total + await transform_async_function_28(item) * 28
    total = total + await transform_async_function_28(item) * 29
    total = total + await transform_async_function_28(item) * 30
    total = total + await transform_async_function_28(item) * 31
    total = total + await transform_async_function_28(item) * 32
    return total


async def handle_async_function_28(item):
    """Split the sequential awaits into two cohesive helpers (order preserved)."""
    return await _handle_first_async_function_28(item) + await _handle_second_async_function_28(item)
```

### Candidate 2

```python
import asyncio

async def transform_async_function_28(item):
    return item * 3

async def handle_async_function_28(item):
    return sum(transform_async_function_28(item) * i for i in range(1, 33))
```

### Candidate 3

```python
import asyncio

async def transform_async_function_28(item):
    return item * 3

async def handle_async_function_28(items):
    return sum(transform_async_function_28(item) * i for i in range(1, 33))
```

### Candidate 4

```python
async def transform_async_function_28(item):
    return item * 3


async def handle_async_function_28(item):
    total = await transform_async_function_28(item)
    total = total + await transform_async_function_28(item) * 2
    total = total + await transform_async_function_28(item) * 3
    total = total + await transform_async_function_28(item) * 4
    total = total + await transform_async_function_28(item) * 5
    total = total + await transform_async_function_28(item) * 6
    total = total + await transform_async_function_28(item) * 7
    total = total + await transform_async_function_28(item) * 8
    total = total + await transform_async_function_28(item) * 9
    total = total + await transform_async_function_28(item) * 10
    total = total + await transform_async_function_28(item) * 11
    total = total + await transform_async_function_28(item) * 12
    total = total + await transform_async_function_28(item) * 13
    total = total + await transform_async_function_28(item) * 14
    total = total + await transform_async_function_28(item) * 15
    total = total + await transform_async_function_28(item) * 16
    total = total + await transform_async_function_28(item) * 17
    total = total + await transform_async_function_28(item) * 18
    total = total + await transform_async_function_28(item) * 19
    total = total + await transform_async_function_28(item) * 20
    total = total + await transform_async_function_28(item) * 21
    total = total + await transform_async_function_28(item) * 22
    total = total + await transform_async_function_28(item) * 23
    total = total + await transform_async_function_28(item) * 24
    total = total + await transform_async_function_28(item) * 25
    total = total + await transform_async_function_28(item) * 26
    total = total + await transform_async_function_28(item) * 27
    total = total + await transform_async_function_28(item) * 28
    total = total + await transform_async_function_28(item) * 29
    total = total + await transform_async_function_28(item) * 30
    total = total + await transform_async_function_28(item) * 31
    total = total + await transform_async_function_28(item) * 32
    return total
```

## `broad-exception-clean-test-01`

Refactoring type: `broad-exception`

### Original code

```python
def read_number_broad_exception_25(raw):
    try:
        return int(raw.strip())
    except (TypeError, ValueError):
        return 0
```

### Candidate 1

```python
def read_number_broad_exception_25(raw):
    try:
        return int(raw.strip())
    except (TypeError, ValueError):
        return 0
```

### Candidate 2

```python
def read_number_broad_exception_25(raw):
    stripped = raw.strip()
    if not stripped.isdigit():
        return 0
    return int(stripped)
```

### Candidate 3

```python
def read_number_broad_exception_25(raw):
    try:
        return int(raw.strip())
    except (TypeError, ValueError):
        return 0
```

### Candidate 4

```python
def read_number_broad_exception_25(raw):
    stripped_raw = raw.strip()
    if stripped_raw.isdigit():
        return int(stripped_raw)
    else:
        return 0
```

## `broad-exception-clean-test-02`

Refactoring type: `broad-exception`

### Original code

```python
import json


def parse_payload_broad_exception_26(raw):
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return {}
```

### Candidate 1

```python
import json


def parse_payload_broad_exception_26(raw):
    try:
        return json.loads(raw)
    except (TypeError, ValueError) as e:
        print(f"Error parsing JSON: {e}")
        return {}
```

### Candidate 2

```python
import json


def parse_payload_broad_exception_26(raw):
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return {}
```

### Candidate 3

```python
import json


def parse_payload_broad_exception_26(raw):
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return {}
```

### Candidate 4

```python
import json


def parse_payload_broad_exception_26(raw):
    try:
        return json.loads(raw)
    except (TypeError, ValueError) as e:
        print(f"Error parsing JSON: {e}")
        return {}
```

## `broad-exception-test-01`

Refactoring type: `broad-exception`

### Original code

```python
def read_number_broad_exception_25(raw):
    try:
        return int(raw.strip())
    except Exception:
        return 0
```

### Candidate 1

```python
import sys

def read_number_broad_exception_25(raw):
    try:
        return int(raw.strip())
    except ValueError:
        print(f"Error: Could not convert '{raw}' to an integer.", file=sys.stderr)
        return 0
```

### Candidate 2

```python
def read_number_broad_exception_25(raw):
    try:
        return int(raw.strip())
    except ValueError:
        return 0
```

### Candidate 3

```python
def read_number_broad_exception_25(raw):
    try:
        return int(raw.strip())
    except (TypeError, ValueError):
        return 0
```

### Candidate 4

```python
def read_number_broad_exception_25(raw):
    try:
        return int(raw.strip())
    except Exception:
        return 0
```

## `broad-exception-test-02`

Refactoring type: `broad-exception`

### Original code

```python
import json


def parse_payload_broad_exception_26(raw):
    try:
        return json.loads(raw)
    except Exception:
        return {}
```

### Candidate 1

```python
import json


def parse_payload_broad_exception_26(raw):
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return {}
```

### Candidate 2

```python
import json


def parse_payload_broad_exception_26(raw):
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
```

### Candidate 3

```python
import json


def parse_payload_broad_exception_26(raw):
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}
```

### Candidate 4

```python
import json


def parse_payload_broad_exception_26(raw):
    try:
        return json.loads(raw)
    except Exception:
        return {}
```

## `broad-exception-test-03`

Refactoring type: `broad-exception`

### Original code

```python
def safe_ratio_broad_exception_27(numerator, denominator):
    try:
        return numerator / denominator
    except Exception:
        return 0
```

### Candidate 1

```python
def safe_ratio_broad_exception_27(numerator, denominator):
    try:
        return numerator / denominator
    except (TypeError, ZeroDivisionError):
        return 0
```

### Candidate 2

```python
def safe_ratio_broad_exception_27(numerator, denominator):
    try:
        return numerator / denominator
    except Exception:
        return 0
```

### Candidate 3

```python
import logging

logger = logging.getLogger(__name__)

def safe_ratio_broad_exception_27(numerator, denominator):
    try:
        return numerator / denominator
    except ZeroDivisionError as e:
        logger.error(f"ZeroDivisionError occurred: {e}")
        return 0
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
        return 0
```

### Candidate 4

```python
import logging

logger = logging.getLogger(__name__)

def safe_ratio_broad_exception_27(numerator, denominator):
    try:
        return numerator / denominator
    except Exception as e:
        logger.error(f"An error occurred during division: {e}")
        return 0
```

## `broad-exception-test-04`

Refactoring type: `broad-exception`

### Original code

```python
def read_number_broad_exception_28(raw):
    try:
        return int(raw.strip())
    except Exception:
        return 0
```

### Candidate 1

```python
def read_number_broad_exception_28(raw):
    try:
        return int(raw.strip())
    except Exception:
        return 0
```

### Candidate 2

```python
def read_number_broad_exception_28(raw):
    try:
        return int(raw.strip())
    except (TypeError, ValueError):
        return 0
```

### Candidate 3

```python
import sys

def read_number_broad_exception_28(raw):
    try:
        return int(raw.strip())
    except ValueError:
        print(f"Error: {raw} is not a valid integer.", file=sys.stderr)
        return 0
```

### Candidate 4

```python
def read_number_broad_exception_28(raw):
    try:
        return int(raw.strip())
    except ValueError:
        return 0
```

## `deep-nesting-clean-test-01`

Refactoring type: `deep-nesting`

### Original code

```python
def evaluate_deep_nesting_25(user, score, level, active):
    if user and score > 35 and level and active:
        return user + score + level
    return 0
```

### Candidate 1

```python
def evaluate_deep_nesting_25(user, score, level, active):
    if user and score > 35 and level and active:
        return user + score + level
    return 0
```

### Candidate 2

```python
def evaluate_deep_nesting_25(user, score, level, active):
    if user and score > 35 and level and active:
        return user + score + level
    return 0
```

### Candidate 3

```python
def evaluate_deep_nesting_25(user, score, level, active):
    if user and score > 35 and level and active:
        return user + score + level
    return 0
```

### Candidate 4

```python
def evaluate_deep_nesting_25(user, score, level, active):
    if all([user, score > 35, level, active]):
        return user + score + level
    return 0
```

## `deep-nesting-clean-test-02`

Refactoring type: `deep-nesting`

### Original code

```python
def summarize_deep_nesting_26(groups, minimum, include_zero):
    """Flatten the nested loops with guard clauses (behaviour preserved)."""
    total = 0
    for group in groups or []:
        for value in group or []:
            if value < minimum:
                continue
            if not include_zero and value == 0:
                continue
            total += value
    return total
```

### Candidate 1

```python
def summarize_deep_nesting_26(groups, minimum, include_zero):
    """Flatten the nested loops with guard clauses (behaviour preserved)."""
    total = 0
    for group in groups or []:
        for value in group or []:
            if value < minimum:
                continue
            if not include_zero and value == 0:
                continue
            total += value
    return total
```

### Candidate 2

```python
def summarize_deep_nesting_26(groups, minimum, include_zero):
    """Flatten the nested loops with guard clauses (behaviour preserved)."""
    total = 0
    for group in groups or []:
        for value in group or []:
            if value < minimum:
                continue
            if not include_zero and value == 0:
                continue
            total += value
    return total
```

### Candidate 3

```python
def summarize_deep_nesting_26(groups, minimum, include_zero):
    """Flatten the nested loops with guard clauses (behaviour preserved)."""
    total = 0
    for group in groups or []:
        for value in group or []:
            if value < minimum:
                continue
            if not include_zero and value == 0:
                continue
            total += value
    return total
```

### Candidate 4

```python
def summarize_deep_nesting_26(groups, minimum, include_zero):
    """Flatten the nested loops with guard clauses (behaviour preserved)."""
    total = 0
    for group in groups or []:
        for value in group or []:
            if value < minimum:
                continue
            if not include_zero and value == 0:
                continue
            total += value
    return total
```

## `deep-nesting-test-01`

Refactoring type: `deep-nesting`

### Original code

```python
def evaluate_deep_nesting_25(user, score, level, active):
    if user:
        if score > 35:
            if level:
                if active:
                    return user + score + level
    return 0
```

### Candidate 1

```python
def evaluate_deep_nesting_25(user, score, level, active):
    if not user or score <= 35 or not level or not active:
        return 0
    return user + score + level
```

### Candidate 2

```python
def evaluate_deep_nesting_25(user, score, level, active):
    if user and score > 35 and level and active:
        return user + score + level
    return 0
```

### Candidate 3

```python
def evaluate_deep_nesting_25(user, score, level, active):
    if user and score > 35 and level and active:
        return user + score + level
    return 0
```

### Candidate 4

```python
def evaluate_deep_nesting_25(user, score, level, active):
    if user:
        if score > 35:
            if level:
                if active:
                    return user + score + level
    return 0
```

## `deep-nesting-test-02`

Refactoring type: `deep-nesting`

### Original code

```python
def summarize_deep_nesting_26(groups, minimum, include_zero):
    total = 0
    if groups:
        for group in groups:
            if group:
                for value in group:
                    if value >= minimum:
                        if include_zero or value != 0:
                            total += value
    return total
```

### Candidate 1

```python
def summarize_deep_nesting_26(groups, minimum, include_zero):
    total = 0
    if groups:
        for group in groups:
            if group:
                for value in group:
                    if value >= minimum:
                        if include_zero or value!= 0:
                            total += value
    return total
```

### Candidate 2

```python
def summarize_deep_nesting_26(groups, minimum, include_zero):
    total = 0
    for group in groups:
        if group:
            for value in group:
                if value >= minimum:
                    total += value
    return total
```

### Candidate 3

```python
def summarize_deep_nesting_26(groups, minimum, include_zero):
    total = 0
    for group in groups:
        for value in group:
            if value >= minimum and (include_zero or value!= 0):
                total += value
    return total
```

### Candidate 4

```python
def summarize_deep_nesting_26(groups, minimum, include_zero):
    """Flatten the nested loops with guard clauses."""
    total = 0
    for group in groups or []:
        for value in group or []:
            if value < minimum:
                continue
            if not include_zero and value == 0:
                continue
            total += value
    return total
```

## `deep-nesting-test-03`

Refactoring type: `deep-nesting`

### Original code

```python
def evaluate_deep_nesting_27(user, score, level, active):
    if user:
        if score > 37:
            if level:
                if active:
                    return user + score + level
    return 0
```

### Candidate 1

```python
def evaluate_deep_nesting_27(user, score, level, active):
    if user:
        if score > 37:
            if level:
                return user + score + level
    return 0
```

### Candidate 2

```python
def evaluate_deep_nesting_27(user, score, level, active):
    if user and score > 37 and level and active:
        return user + score + level
    return 0
```

### Candidate 3

```python
def evaluate_deep_nesting_27(user, score, level, active):
    if not user or score <= 37 or not level or not active:
        return 0
    return user + score + level
```

### Candidate 4

```python
def evaluate_deep_nesting_27(user, score, level, active):
    if user:
        if score > 37:
            if level:
                if active:
                    return user + score + level
    return 0
```

## `deep-nesting-test-04`

Refactoring type: `deep-nesting`

### Original code

```python
def summarize_deep_nesting_28(groups, minimum, include_zero):
    total = 0
    if groups:
        for group in groups:
            if group:
                for value in group:
                    if value >= minimum:
                        if include_zero or value != 0:
                            total += value
    return total
```

### Candidate 1

```python
def summarize_deep_nesting_28(groups, minimum, include_zero):
    total = 0
    for group in groups or []:
        for value in group or []:
            if value >= minimum and (include_zero or value!= 0):
                total += value
    return total
```

### Candidate 2

```python
def summarize_deep_nesting_28(groups, minimum, include_zero):
    total = 0
    if groups:
        for group in groups:
            if group:
                for value in group:
                    if value >= minimum:
                        if include_zero or value!= 0:
                            total += value
    return total
```

### Candidate 3

```python
def summarize_deep_nesting_28(groups, minimum, include_zero):
    """Flatten the nested loops into a chain of generators."""
    return sum(value
               for group in groups
               if group
               for value in group
               if value >= minimum
               if include_zero or value!= 0)
```

### Candidate 4

```python
def summarize_deep_nesting_28(groups, minimum, include_zero):
    def is_valid_value(value):
        return value >= minimum and (include_zero or value!= 0)

    total = 0
    for group in groups:
        if group:
            for value in group:
                if is_valid_value(value):
                    total += value
    return total
```

## `duplicate-code-clean-test-01`

Refactoring type: `duplicate-code`

### Original code

```python
def _sum_positive_duplicate_code_25(records):
    total = 0
    for record in records:
        if record > 0:
            total += record
    return total


def summarize_duplicate_code_25_a(records):
    return _sum_positive_duplicate_code_25(records)

def summarize_duplicate_code_25_b(records):
    return _sum_positive_duplicate_code_25(records)
```

### Candidate 1

```python
def _sum_positive_duplicate_code_25(records):
    total = 0
    for record in records:
        if record > 0:
            total += record
    return total


def summarize_duplicate_code_25_a(records):
    return _sum_positive_duplicate_code_25(records)

def summarize_duplicate_code_25_b(records):
    return _sum_positive_duplicate_code_25(records)
```

### Candidate 2

```python
def _sum_positive_duplicate_code_25(records):
    total = 0
    for record in records:
        if record > 0:
            total += record
    return total

def summarize_duplicate_code_25(records):
    return _sum_positive_duplicate_code_25(records)

def summarize_duplicate_code_25_b(records):
    return _sum_positive_duplicate_code_25(records)
```

### Candidate 3

```python
def _sum_positive_duplicate_code_25(records):
    return sum(record for record in records if record > 0)


def summarize_duplicate_code_25_a(records):
    return _sum_positive_duplicate_code_25(records)

def summarize_duplicate_code_25_b(records):
    return _sum_positive_duplicate_code_25(records)
```

### Candidate 4

```python
def _sum_positive_duplicate_code_25(records):
    total = 0
    for record in records:
        if record > 0:
            total += record
    return total


def summarize_duplicate_code_25_a(records):
    return _sum_positive_duplicate_code_25(records)

def summarize_duplicate_code_25_b(records):
    return _sum_positive_duplicate_code_25(records)
```

## `duplicate-code-clean-test-02`

Refactoring type: `duplicate-code`

### Original code

```python
def _parse_pairs_duplicate_code_26(raw):
    parts = raw.split(',')
    result = {}
    for part in parts:
        if '=' in part:
            key, value = part.split('=', 1)
            result[key.strip()] = value.strip()
    return result


def parse_duplicate_code_26_left(raw):
    return _parse_pairs_duplicate_code_26(raw)

def parse_duplicate_code_26_right(raw):
    return _parse_pairs_duplicate_code_26(raw)
```

### Candidate 1

```python
def _parse_pairs_duplicate_code_26(raw):
    parts = raw.split(',')
    result = {}
    for part in parts:
        if '=' in part:
            key, value = part.split('=', 1)
            result[key.strip()] = value.strip()
    return result


def parse_duplicate_code_26_left(raw):
    return _parse_pairs_duplicate_code_26(raw)


def parse_duplicate_code_26_right(raw):
    return _parse_pairs_duplicate_code_26(raw)
```

### Candidate 2

```python
def _parse_pairs_duplicate_code_26(raw):
    parts = raw.split(',')
    result = {}
    for part in parts:
        if '=' in part:
            key, value = part.split('=', 1)
            result[key.strip()] = value.strip()
    return result


def parse_duplicate_code_26_left(raw):
    return _parse_pairs_duplicate_code_26(raw)

def parse_duplicate_code_26_right(raw):
    return _parse_pairs_duplicate_code_26(raw)
```

### Candidate 3

```python
def _parse_pairs_duplicate_code_26(raw):
    parts = raw.split(',')
    result = {}
    for part in parts:
        if '=' in part:
            key, value = part.split('=', 1)
            result[key.strip()] = value.strip()
    return result


def parse_duplicate_code_26_left(raw):
    return _parse_pairs_duplicate_code_26(raw)

def parse_duplicate_code_26_right(raw):
    return _parse_pairs_duplicate_code_26(raw)
```

### Candidate 4

```python
def _parse_pairs_duplicate_code_26(raw):
    parts = raw.split(',')
    result = {}
    for part in parts:
        if '=' in part:
            key, value = part.split('=', 1)
            result[key.strip()] = value.strip()
    return result


def parse_duplicate_code_26_left(raw):
    return _parse_pairs_duplicate_code_26(raw)

def parse_duplicate_code_26_right(raw):
    return _parse_pairs_duplicate_code_26(raw)
```

## `duplicate-code-test-01`

Refactoring type: `duplicate-code`

### Original code

```python
def summarize_duplicate_code_25_a(records):
    total = 0
    for record in records:
        if record > 0:
            total += record
    return total


def summarize_duplicate_code_25_b(records):
    total = 0
    for record in records:
        if record > 0:
            total += record
    return total
```

### Candidate 1

```python
def calculate_total_positive(records):
    total = 0
    for record in records:
        if record > 0:
            total += record
    return total


def summarize_duplicate_code_25_a(records):
    return calculate_total_positive(records)


def summarize_duplicate_code_25_b(records):
    return calculate_total_positive(records)
```

### Candidate 2

```python
def summarize_duplicate_code_25_a(records):
    return _summarize_records(records)


def summarize_duplicate_code_25_b(records):
    return _summarize_records(records)


def _summarize_records(records):
    total = 0
    for record in records:
        if record > 0:
            total += record
    return total
```

### Candidate 3

```python
def summarize_duplicate_code_25_a(records):
    total = 0
    for record in records:
        if record > 0:
            total += record
    return total


def summarize_duplicate_code_25_b(records):
    total = 0
    for record in records:
        if record > 0:
            total += record
    return total
```

### Candidate 4

```python
def _sum_positive_duplicate_code_25(records):
    total = 0
    for record in records:
        if record > 0:
            total += record
    return total


def summarize_duplicate_code_25_a(records):
    return _sum_positive_duplicate_code_25(records)

def summarize_duplicate_code_25_b(records):
    return _sum_positive_duplicate_code_25(records)
```

## `duplicate-code-test-02`

Refactoring type: `duplicate-code`

### Original code

```python
def parse_duplicate_code_26_left(raw):
    parts = raw.split(',')
    result = {}
    for part in parts:
        if '=' in part:
            key, value = part.split('=', 1)
            result[key.strip()] = value.strip()
    return result


def parse_duplicate_code_26_right(raw):
    parts = raw.split(',')
    result = {}
    for part in parts:
        if '=' in part:
            key, value = part.split('=', 1)
            result[key.strip()] = value.strip()
    return result
```

### Candidate 1

```python
def parse_duplicate_code_26(raw):
    parts = raw.split(',')
    result = {}
    for part in parts:
        if '=' in part:
            key, value = part.split('=', 1)
            result[key.strip()] = value.strip()
    return result

def parse_duplicate_code_helper(raw):
    parts = raw.split(',')
    result = {}
    for part in parts:
        if '=' in part:
            key, value = part.split('=', 1)
            result[key.strip()] = value.strip()
    return result

def parse_duplicate_code_26_left(raw):
    return parse_duplicate_code_helper(raw)

def parse_duplicate_code_26_right(raw):
    return parse_duplicate_code_helper(raw)
```

### Candidate 2

```python
def parse_duplicate_code_26_left(raw):
    parts = raw.split(',')
    result = {}
    for part in parts:
        if '=' in part:
            key, value = part.split('=', 1)
            result[key.strip()] = value.strip()
    return result


def parse_duplicate_code_26_right(raw):
    parts = raw.split(',')
    result = {}
    for part in parts:
        if '=' in part:
            key, value = part.split('=', 1)
            result[key.strip()] = value.strip()
    return result
```

### Candidate 3

```python
def _parse_pair_duplicate_code_26(raw):
    parts = raw.split(',')
    result = {}
    for part in parts:
        if '=' in part:
            key, value = part.split('=', 1)
            result[key.strip()] = value.strip()
    return result


def parse_duplicate_code_26_left(raw):
    return _parse_pair_duplicate_code_26(raw)

def parse_duplicate_code_26_right(raw):
    return _parse_pair_duplicate_code_26(raw)
```

### Candidate 4

```python
def parse_duplicate_code_26(raw):
    parts = raw.split(',')
    result = {}
    for part in parts:
        if '=' in part:
            key, value = part.split('=', 1)
            result[key.strip()] = value.strip()
    return result

def parse_duplicate_code_26_helper(raw):
    parts = raw.split(',')
    result = {}
    for part in parts:
        if '=' in part:
            key, value = part.split('=', 1)
            result[key.strip()] = value.strip()
    return result

def parse_duplicate_code_26_left(raw):
    return parse_duplicate_code_26_helper(raw)

def parse_duplicate_code_26_right(raw):
    return parse_duplicate_code_26_helper(raw)
```

## `duplicate-code-test-03`

Refactoring type: `duplicate-code`

### Original code

```python
def summarize_duplicate_code_27_a(records):
    total = 0
    for record in records:
        if record > 0:
            total += record
    return total


def summarize_duplicate_code_27_b(records):
    total = 0
    for record in records:
        if record > 0:
            total += record
    return total
```

### Candidate 1

```python
def _sum_positive_duplicate_code_27(records):
    total = 0
    for record in records:
        if record > 0:
            total += record
    return total


def summarize_duplicate_code_27_a(records):
    return _sum_positive_duplicate_code_27(records)

def summarize_duplicate_code_27_b(records):
    return _sum_positive_duplicate_code_27(records)
```

### Candidate 2

```python
def summarize_duplicate_code_27(records):
    return sum(record for record in records if record > 0)


def summarize_duplicate_code_27_a(records):
    return summarize_duplicate_code_27(records)


def summarize_duplicate_code_27_b(records):
    return summarize_duplicate_code_27(records)
```

### Candidate 3

```python
def summarize_duplicate_code_27_a(records):
    total = 0
    for record in records:
        if record > 0:
            total += record
    return total


def summarize_duplicate_code_27_b(records):
    total = 0
    for record in records:
        if record > 0:
            total += record
    return total
```

### Candidate 4

```python
def summarize_duplicate_code_27(records):
    def calculate_total():
        total = 0
        for record in records:
            if record > 0:
                total += record
        return total

    return calculate_total()

def summarize_duplicate_code_27_a(records):
    return summarize_duplicate_code_27(records)

def summarize_duplicate_code_27_b(records):
    return summarize_duplicate_code_27(records)
```

## `duplicate-code-test-04`

Refactoring type: `duplicate-code`

### Original code

```python
def parse_duplicate_code_28_left(raw):
    parts = raw.split(',')
    result = {}
    for part in parts:
        if '=' in part:
            key, value = part.split('=', 1)
            result[key.strip()] = value.strip()
    return result


def parse_duplicate_code_28_right(raw):
    parts = raw.split(',')
    result = {}
    for part in parts:
        if '=' in part:
            key, value = part.split('=', 1)
            result[key.strip()] = value.strip()
    return result
```

### Candidate 1

```python
def parse_duplicate_code_28(raw):
    parts = raw.split(',')
    result = {}
    for part in parts:
        if '=' in part:
            key, value = part.split('=', 1)
            result[key.strip()] = value.strip()
    return result


def parse_duplicate_code_helper(raw):
    parts = raw.split(',')
    result = {}
    for part in parts:
        if '=' in part:
            key, value = part.split('=', 1)
            result[key.strip()] = value.strip()
    return result


def parse_duplicate_code_28_left(raw):
    return parse_duplicate_code_helper(raw)


def parse_duplicate_code_28_right(raw):
    return parse_duplicate_code_helper(raw)
```

### Candidate 2

```python
def parse_duplicate_code_28_helper(raw):
    result = {}
    for part in raw.split(','):
        if '=' in part:
            key, value = part.split('=', 1)
            result[key.strip()] = value.strip()
    return result


def parse_duplicate_code_28_left(raw):
    return parse_duplicate_code_28_helper(raw)


def parse_duplicate_code_28_right(raw):
    return parse_duplicate_code_28_helper(raw)
```

### Candidate 3

```python
def _parse_pairs_duplicate_code_28(raw):
    parts = raw.split(',')
    result = {}
    for part in parts:
        if '=' in part:
            key, value = part.split('=', 1)
            result[key.strip()] = value.strip()
    return result


def parse_duplicate_code_28_left(raw):
    return _parse_pairs_duplicate_code_28(raw)


def parse_duplicate_code_28_right(raw):
    return _parse_pairs_duplicate_code_28(raw)
```

### Candidate 4

```python
def parse_duplicate_code_28_left(raw):
    parts = raw.split(',')
    result = {}
    for part in parts:
        if '=' in part:
            key, value = part.split('=', 1)
            result[key.strip()] = value.strip()
    return result


def parse_duplicate_code_28_right(raw):
    parts = raw.split(',')
    result = {}
    for part in parts:
        if '=' in part:
            key, value = part.split('=', 1)
            result[key.strip()] = value.strip()
    return result
```

## `high-complexity-clean-test-01`

Refactoring type: `high-complexity`

### Original code

```python
_ROUTES_HIGH_COMPLEXITY_25 = {
    'HIGH_COMPLEXITY_2501': 10,
    'HIGH_COMPLEXITY_2502': 20,
    'HIGH_COMPLEXITY_2503': 30,
    'HIGH_COMPLEXITY_2504': 40,
    'HIGH_COMPLEXITY_2505': 50,
    'HIGH_COMPLEXITY_2506': 60,
    'HIGH_COMPLEXITY_2507': 70,
    'HIGH_COMPLEXITY_2508': 80,
    'HIGH_COMPLEXITY_2509': 90,
    'HIGH_COMPLEXITY_2510': 100,
    'HIGH_COMPLEXITY_2511': 110,
}

def route_high_complexity_25(event_code):
    """Replace the decision chain with table-driven dispatch (behaviour preserved)."""
    return _ROUTES_HIGH_COMPLEXITY_25.get(event_code, 0)
```

### Candidate 1

```python
_ROUTES_HIGH_COMPLEXITY_25 = {
    'HIGH_COMPLEXITY_2501': 10,
    'HIGH_COMPLEXITY_2502': 20,
    'HIGH_COMPLEXITY_2503': 30,
    'HIGH_COMPLEXITY_2504': 40,
    'HIGH_COMPLEXITY_2505': 50,
    'HIGH_COMPLEXITY_2506': 60,
    'HIGH_COMPLEXITY_2507': 70,
    'HIGH_COMPLEXITY_2508': 80,
    'HIGH_COMPLEXITY_2509': 90,
    'HIGH_COMPLEXITY_2510': 100,
    'HIGH_COMPLEXITY_2511': 110,
}

def route_high_complexity_25(event_code):
    """Replace the decision chain with table-driven dispatch (behaviour preserved)."""
    return _ROUTES_HIGH_COMPLEXITY_25.get(event_code, 0)
```

### Candidate 2

```python
_ROUTES_HIGH_COMPLEXITY_25 = {
    'HIGH_COMPLEXITY_2501': 10,
    'HIGH_COMPLEXITY_2502': 20,
    'HIGH_COMPLEXITY_2503': 30,
    'HIGH_COMPLEXITY_2504': 40,
    'HIGH_COMPLEXITY_2505': 50,
    'HIGH_COMPLEXITY_2506': 60,
    'HIGH_COMPLEXITY_2507': 70,
    'HIGH_COMPLEXITY_2508': 80,
    'HIGH_COMPLEXITY_2509': 90,
    'HIGH_COMPLEXITY_2510': 100,
    'HIGH_COMPLEXITY_2511': 110,
}

def route_high_complexity_25(event_code):
    """Replace the decision chain with table-driven dispatch (behaviour preserved)."""
    return _ROUTES_HIGH_COMPLEXITY_25.get(event_code, 0)
```

### Candidate 3

```python
_ROUTES_HIGH_COMPLEXITY_25 = {
    'HIGH_COMPLEXITY_2501': 10,
    'HIGH_COMPLEXITY_2502': 20,
    'HIGH_COMPLEXITY_2503': 30,
    'HIGH_COMPLEXITY_2504': 40,
    'HIGH_COMPLEXITY_2505': 50,
    'HIGH_COMPLEXITY_2506': 60,
    'HIGH_COMPLEXITY_2507': 70,
    'HIGH_COMPLEXITY_2508': 80,
    'HIGH_COMPLEXITY_2509': 90,
    'HIGH_COMPLEXITY_2510': 100,
    'HIGH_COMPLEXITY_2511': 110,
}

def route_high_complexity_25(event_code):
    """Replace the decision chain with table-driven dispatch (behaviour preserved)."""
    return _ROUTES_HIGH_COMPLEXITY_25.get(event_code, 0)
```

### Candidate 4

```python
_ROUTES_HIGH_COMPLEXITY_25 = {
    'HIGH_COMPLEXITY_2501': 10,
    'HIGH_COMPLEXITY_2502': 20,
    'HIGH_COMPLEXITY_2503': 30,
    'HIGH_COMPLEXITY_2504': 40,
    'HIGH_COMPLEXITY_2505': 50,
    'HIGH_COMPLEXITY_2506': 60,
    'HIGH_COMPLEXITY_2507': 70,
    'HIGH_COMPLEXITY_2508': 80,
    'HIGH_COMPLEXITY_2509': 90,
    'HIGH_COMPLEXITY_2510': 100,
    'HIGH_COMPLEXITY_2511': 110,
}

def route_high_complexity_25(event_code):
    """Replace the decision chain with table-driven dispatch (behaviour preserved)."""
    return _ROUTES_HIGH_COMPLEXITY_25.get(event_code, 0)
```

## `high-complexity-clean-test-02`

Refactoring type: `high-complexity`

### Original code

```python
_GRADE_BANDS_HIGH_COMPLEXITY_26 = (
    (95, 'A+'),
    (90, 'A'),
    (85, 'A-'),
    (80, 'B+'),
    (75, 'B'),
    (70, 'B-'),
    (65, 'C+'),
    (60, 'C'),
    (55, 'C-'),
    (50, 'D+'),
    (45, 'D'),
    (40, 'D-'),
)

def classify_high_complexity_26(score):
    """Replace the decision chain with a data table (behaviour preserved)."""
    for threshold, grade in _GRADE_BANDS_HIGH_COMPLEXITY_26:
        if score >= threshold:
            return grade
    return 'F'
```

### Candidate 1

```python
_GRADE_BANDS_HIGH_COMPLEXITY_26 = (
    (95, 'A+'),
    (90, 'A'),
    (85, 'A-'),
    (80, 'B+'),
    (75, 'B'),
    (70, 'B-'),
    (65, 'C+'),
    (60, 'C'),
    (55, 'C-'),
    (50, 'D+'),
    (45, 'D'),
    (40, 'D-'),
)

def classify_high_complexity_26(score):
    """Replace the decision chain with a data table (behaviour preserved)."""
    grade_map = {threshold: grade for threshold, grade in _GRADE_BANDS_HIGH_COMPLEXITY_26}
    return grade_map.get(score, 'F')
```

### Candidate 2

```python
_GRADE_BANDS_HIGH_COMPLEXITY_26 = (
    (95, 'A+'),
    (90, 'A'),
    (85, 'A-'),
    (80, 'B+'),
    (75, 'B'),
    (70, 'B-'),
    (65, 'C+'),
    (60, 'C'),
    (55, 'C-'),
    (50, 'D+'),
    (45, 'D'),
    (40, 'D-'),
)

def classify_high_complexity_26(score):
    """Replace the decision chain with a data table (behaviour preserved)."""
    for threshold, grade in _GRADE_BANDS_HIGH_COMPLEXITY_26:
        if score >= threshold:
            return grade
    return 'F'
```

### Candidate 3

```python
_GRADE_BANDS_HIGH_COMPLEXITY_26 = {
    95: 'A+',
    90: 'A',
    85: 'A-',
    80: 'B+',
    75: 'B',
    70: 'B-',
    65: 'C+',
    60: 'C',
    55: 'C-',
    50: 'D+',
    45: 'D',
    40: 'D-',
}

def classify_high_complexity_26(score):
    """Replace the decision chain with a data table (behaviour preserved)."""
    return _GRADE_BANDS_HIGH_COMPLEXITY_26.get(score, 'F')
```

### Candidate 4

```python
_GRADE_BANDS_HIGH_COMPLEXITY_26 = (
    (95, 'A+'),
    (90, 'A'),
    (85, 'A-'),
    (80, 'B+'),
    (75, 'B'),
    (70, 'B-'),
    (65, 'C+'),
    (60, 'C'),
    (55, 'C-'),
    (50, 'D+'),
    (45, 'D'),
    (40, 'D-'),
)

def classify_high_complexity_26(score):
    """Replace the decision chain with a data table (behaviour preserved)."""
    for threshold, grade in _GRADE_BANDS_HIGH_COMPLEXITY_26:
        if score >= threshold:
            return grade
    return 'F'
```

## `high-complexity-test-01`

Refactoring type: `high-complexity`

### Original code

```python
def route_high_complexity_25(event_code):
    if event_code == 'HIGH_COMPLEXITY_2501':
        return 10
    elif event_code == 'HIGH_COMPLEXITY_2502':
        return 20
    elif event_code == 'HIGH_COMPLEXITY_2503':
        return 30
    elif event_code == 'HIGH_COMPLEXITY_2504':
        return 40
    elif event_code == 'HIGH_COMPLEXITY_2505':
        return 50
    elif event_code == 'HIGH_COMPLEXITY_2506':
        return 60
    elif event_code == 'HIGH_COMPLEXITY_2507':
        return 70
    elif event_code == 'HIGH_COMPLEXITY_2508':
        return 80
    elif event_code == 'HIGH_COMPLEXITY_2509':
        return 90
    elif event_code == 'HIGH_COMPLEXITY_2510':
        return 100
    elif event_code == 'HIGH_COMPLEXITY_2511':
        return 110
    return 0
```

### Candidate 1

```python
def route_high_complexity_25(event_code):
    # Use a dictionary to map event codes to their corresponding values
    event_to_value = {
        'HIGH_COMPLEXITY_2501': 10,
        'HIGH_COMPLEXITY_2502': 20,
        'HIGH_COMPLEXITY_2503': 30,
        'HIGH_COMPLEXITY_2504': 40,
        'HIGH_COMPLEXITY_2505': 50,
        'HIGH_COMPLEXITY_2506': 60,
        'HIGH_COMPLEXITY_2507': 70,
        'HIGH_COMPLEXITY_2508': 80,
        'HIGH_COMPLEXITY_2509': 90,
        'HIGH_COMPLEXITY_2510': 100,
        'HIGH_COMPLEXITY_2511': 110
    }
    
    # Return the value from the dictionary if the event code exists, otherwise return 0
    return event_to_value.get(event_code, 0)
```

### Candidate 2

```python
_ROUTES_HIGH_COMPLEXITY_25 = {
    'HIGH_COMPLEXITY_2501': 10,
    'HIGH_COMPLEXITY_2502': 20,
    'HIGH_COMPLEXITY_2503': 30,
    'HIGH_COMPLEXITY_2504': 40,
    'HIGH_COMPLEXITY_2505': 50,
    'HIGH_COMPLEXITY_2506': 60,
    'HIGH_COMPLEXITY_2507': 70,
    'HIGH_COMPLEXITY_2508': 80,
    'HIGH_COMPLEXITY_2509': 90,
    'HIGH_COMPLEXITY_2510': 100,
    'HIGH_COMPLEXITY_2511': 110,
}

def route_high_complexity_25(event_code):
    """Replace the chain of conditional expressions with table-driven dispatch (behaviour preserved)."""
    return _ROUTES_HIGH_COMPLEXITY_25.get(event_code, 0)
```

### Candidate 3

```python
def route_high_complexity_25(event_code):
    match event_code:
        case 'HIGH_COMPLEXITY_2501':
            return 10
        case 'HIGH_COMPLEXITY_2502':
            return 20
        case 'HIGH_COMPLEXITY_2503':
            return 30
        case 'HIGH_COMPLEXITY_2504':
            return 40
        case 'HIGH_COMPLEXITY_2505':
            return 50
        case 'HIGH_COMPLEXITY_2506':
            return 60
        case 'HIGH_COMPLEXITY_2507':
            return 70
        case 'HIGH_COMPLEXITY_2508':
            return 80
        case 'HIGH_COMPLEXITY_2509':
            return 90
        case 'HIGH_COMPLEXITY_2510':
            return 100
        case 'HIGH_COMPLEXITY_2511':
            return 110
        case _:
            return 0
```

### Candidate 4

```python
_ROUTES_HIGH_COMPLEXITY_25 = {
    'HIGH_COMPLEXITY_2501': 10,
    'HIGH_COMPLEXITY_2502': 20,
    'HIGH_COMPLEXITY_2503': 30,
    'HIGH_COMPLEXITY_2504': 40,
    'HIGH_COMPLEXITY_2505': 50,
    'HIGH_COMPLEXITY_2506': 60,
    'HIGH_COMPLEXITY_2507': 70,
    'HIGH_COMPLEXITY_2508': 80,
    'HIGH_COMPLEXITY_2509': 90,
    'HIGH_COMPLEXITY_2510': 100,
    'HIGH_COMPLEXITY_2511': 110,
}

def route_high_complexity_25(event_code):
    """Replace the decision chain with table-driven dispatch (behaviour preserved)."""
    return _ROUTES_HIGH_COMPLEXITY_25.get(event_code, 0)
```

## `high-complexity-test-02`

Refactoring type: `high-complexity`

### Original code

```python
def classify_high_complexity_26(score):
    if score >= 95:
        return 'A+'
    elif score >= 90:
        return 'A'
    elif score >= 85:
        return 'A-'
    elif score >= 80:
        return 'B+'
    elif score >= 75:
        return 'B'
    elif score >= 70:
        return 'B-'
    elif score >= 65:
        return 'C+'
    elif score >= 60:
        return 'C'
    elif score >= 55:
        return 'C-'
    elif score >= 50:
        return 'D+'
    elif score >= 45:
        return 'D'
    elif score >= 40:
        return 'D-'
    return 'F'
```

### Candidate 1

```python
def classify_high_complexity_26(score):
    if score >= 95:
        return 'A+'
    elif score >= 90:
        return 'A'
    elif score >= 85:
        return 'A-'
    elif score >= 80:
        return 'B+'
    elif score >= 75:
        return 'B'
    elif score >= 70:
        return 'B-'
    elif score >= 65:
        return 'C+'
    elif score >= 60:
        return 'C'
    elif score >= 55:
        return 'C-'
    elif score >= 50:
        return 'D+'
    elif score >= 45:
        return 'D'
    elif score >= 40:
        return 'D-'
    return 'F'
```

### Candidate 2

```python
def classify_high_complexity_26(score):
    grades = [
        ('A+', 95),
        ('A', 90),
        ('A-', 85),
        ('B+', 80),
        ('B', 75),
        ('B-', 70),
        ('C+', 65),
        ('C', 60),
        ('C-', 55),
        ('D+', 50),
        ('D', 45),
        ('D-', 40),
        ('F', 0)
    ]
    
    for grade, cutoff in grades:
        if score >= cutoff:
            return grade
    return 'F'
```

### Candidate 3

```python
_GRADE_BANDS_HIGH_COMPLEXITY_26 = (
    (95, 'A+'),
    (90, 'A'),
    (85, 'A-'),
    (80, 'B+'),
    (75, 'B'),
    (70, 'B-'),
    (65, 'C+'),
    (60, 'C'),
    (55, 'C-'),
    (50, 'D+'),
    (45, 'D'),
    (40, 'D-'),
)

def classify_high_complexity_26(score):
    """Replace the decision chain with data table (behaviour preserved)."""
    for threshold, grade in _GRADE_BANDS_HIGH_COMPLEXITY_26:
        if score >= threshold:
            return grade
    return 'F'
```

### Candidate 4

```python
def classify_high_complexity_26(score):
    grades = {
        95: 'A+',
        90: 'A',
        85: 'A-',
        80: 'B+',
        75: 'B',
        70: 'B-',
        65: 'C+',
        60: 'C',
        55: 'C-',
        50: 'D+',
        45: 'D',
        40: 'D-'
    }
    
    for threshold, grade in grades.items():
        if score >= threshold:
            return grade
    
    return 'F'
```

## `high-complexity-test-03`

Refactoring type: `high-complexity`

### Original code

```python
def route_high_complexity_27(event_code):
    if event_code == 'HIGH_COMPLEXITY_2701':
        return 10
    elif event_code == 'HIGH_COMPLEXITY_2702':
        return 20
    elif event_code == 'HIGH_COMPLEXITY_2703':
        return 30
    elif event_code == 'HIGH_COMPLEXITY_2704':
        return 40
    elif event_code == 'HIGH_COMPLEXITY_2705':
        return 50
    elif event_code == 'HIGH_COMPLEXITY_2706':
        return 60
    elif event_code == 'HIGH_COMPLEXITY_2707':
        return 70
    elif event_code == 'HIGH_COMPLEXITY_2708':
        return 80
    elif event_code == 'HIGH_COMPLEXITY_2709':
        return 90
    elif event_code == 'HIGH_COMPLEXITY_2710':
        return 100
    elif event_code == 'HIGH_COMPLEXITY_2711':
        return 110
    return 0
```

### Candidate 1

```python
_ROUTES_HIGH_COMPLEXITY_27 = {
    'HIGH_COMPLEXITY_2701': 10,
    'HIGH_COMPLEXITY_2702': 20,
    'HIGH_COMPLEXITY_2703': 30,
    'HIGH_COMPLEXITY_2704': 40,
    'HIGH_COMPLEXITY_2705': 50,
    'HIGH_COMPLEXITY_2706': 60,
    'HIGH_COMPLEXITY_2707': 70,
    'HIGH_COMPLEXITY_2708': 80,
    'HIGH_COMPLEXITY_2709': 90,
    'HIGH_COMPLEXITY_2710': 100,
    'HIGH_COMPLEXITY_2711': 110,
}

def route_high_complexity_27(event_code):
    """Replace the decision chain with table-driven dispatch (behaviour preserved)."""
    return _ROUTES_HIGH_COMPLEXITY_27.get(event_code, 0)
```

### Candidate 2

```python
def route_high_complexity_27(event_code):
    code_to_return = {
        'HIGH_COMPLEXITY_2701': 10,
        'HIGH_COMPLEXITY_2702': 20,
        'HIGH_COMPLEXITY_2703': 30,
        'HIGH_COMPLEXITY_2704': 40,
        'HIGH_COMPLEXITY_2705': 50,
        'HIGH_COMPLEXITY_2706': 60,
        'HIGH_COMPLEXITY_2707': 70,
        'HIGH_COMPLEXITY_2708': 80,
        'HIGH_COMPLEXITY_2709': 90,
        'HIGH_COMPLEXITY_2710': 100,
        'HIGH_COMPLEXITY_2711': 110,
    }
    return code_to_return.get(event_code, 0)
```

### Candidate 3

```python
def route_high_complexity_27(event_code):
    match event_code:
        case 'HIGH_COMPLEXITY_2701': return 10
        case 'HIGH_COMPLEXITY_2702': return 20
        case 'HIGH_COMPLEXITY_2703': return 30
        case 'HIGH_COMPLEXITY_2704': return 40
        case 'HIGH_COMPLEXITY_2705': return 50
        case 'HIGH_COMPLEXITY_2706': return 60
        case 'HIGH_COMPLEXITY_2707': return 70
        case 'HIGH_COMPLEXITY_2708': return 80
        case 'HIGH_COMPLEXITY_2709': return 90
        case 'HIGH_COMPLEXITY_2710': return 100
        case 'HIGH_COMPLEXITY_2711': return 110
        case _: return 0
```

### Candidate 4

```python
_ROUTES_HIGH_COMPLEXITY_27 = {
    'HIGH_COMPLEXITY_2701': 10,
    'HIGH_COMPLEXITY_2702': 20,
    'HIGH_COMPLEXITY_2703': 30,
    'HIGH_COMPLEXITY_2704': 40,
    'HIGH_COMPLEXITY_2705': 50,
    'HIGH_COMPLEXITY_2706': 60,
    'HIGH_COMPLEXITY_2707': 70,
    'HIGH_COMPLEXITY_2708': 80,
    'HIGH_COMPLEXITY_2709': 90,
    'HIGH_COMPLEXITY_2710': 100,
    'HIGH_COMPLEXITY_2711': 110,
}

def route_high_complexity_27(event_code):
    """Replace the decision chain with table-driven dispatch (behaviour preserved)."""
    return _ROUTES_HIGH_COMPLEXITY_27.get(event_code, 0)
```

## `high-complexity-test-04`

Refactoring type: `high-complexity`

### Original code

```python
def classify_high_complexity_28(score):
    if score >= 95:
        return 'A+'
    elif score >= 90:
        return 'A'
    elif score >= 85:
        return 'A-'
    elif score >= 80:
        return 'B+'
    elif score >= 75:
        return 'B'
    elif score >= 70:
        return 'B-'
    elif score >= 65:
        return 'C+'
    elif score >= 60:
        return 'C'
    elif score >= 55:
        return 'C-'
    elif score >= 50:
        return 'D+'
    elif score >= 45:
        return 'D'
    elif score >= 40:
        return 'D-'
    return 'F'
```

### Candidate 1

```python
def classify_high_complexity_28(score):
    if score >= 95:
        return 'A+'
    elif score >= 90:
        return 'A'
    elif score >= 85:
        return 'A-'
    elif score >= 80:
        return 'B+'
    elif score >= 75:
        return 'B'
    elif score >= 70:
        return 'B-'
    elif score >= 65:
        return 'C+'
    elif score >= 60:
        return 'C'
    elif score >= 55:
        return 'C-'
    elif score >= 50:
        return 'D+'
    elif score >= 45:
        return 'D'
    elif score >= 40:
        return 'D-'
    return 'F'
```

### Candidate 2

```python
def classify_high_complexity_28(score):
    grades = {
        95: 'A+', 90: 'A', 85: 'A-', 80: 'B+', 75: 'B',
        70: 'B-', 65: 'C+', 60: 'C', 55: 'C-', 50: 'D+',
        45: 'D', 40: 'D-'
    }
    
    for threshold, grade in grades.items():
        if score >= threshold:
            return grade
    
    return 'F'
```

### Candidate 3

```python
def classify_high_complexity_28(score):
    grades = {
        95: 'A+',
        90: 'A',
        85: 'A-',
        80: 'B+',
        75: 'B',
        70: 'B-',
        65: 'C+',
        60: 'C',
        55: 'C-',
        50: 'D+',
        45: 'D',
        40: 'D-',
    }
    for threshold, grade in grades.items():
        if score >= threshold:
            return grade
    return 'F'
```

### Candidate 4

```python
_GRADE_BANDS_HIGH_COMPLEXITY_28 = (
    (95, 'A+'),
    (90, 'A'),
    (85, 'A-'),
    (80, 'B+'),
    (75, 'B'),
    (70, 'B-'),
    (65, 'C+'),
    (60, 'C'),
    (55, 'C-'),
    (50, 'D+'),
    (45, 'D'),
    (40, 'D-'),
)

def classify_high_complexity_28(score):
    """Replace the decision chain with a data table (behaviour preserved)."""
    for threshold, grade in _GRADE_BANDS_HIGH_COMPLEXITY_28:
        if score >= threshold:
            return grade
    return 'F'
```

## `long-function-clean-test-01`

Refactoring type: `long-function`

### Original code

```python
def _aggregate_long_function_25_first(seed):
    total = seed
    total = total * 1 + 1
    total = total * 2 + 2
    total = total * 3 + 3
    total = total * 4 + 4
    total = total * 5 + 5
    total = total * 6 + 6
    total = total * 7 + 7
    total = total * 8 + 8
    total = total * 9 + 9
    total = total * 10 + 10
    total = total * 11 + 11
    total = total * 12 + 12
    total = total * 13 + 13
    total = total * 14 + 14
    total = total * 15 + 15
    total = total * 16 + 16
    return total

def _aggregate_long_function_25_second(total):
    total = total * 17 + 17
    total = total * 18 + 18
    total = total * 19 + 19
    total = total * 20 + 20
    total = total * 21 + 21
    total = total * 22 + 22
    total = total * 23 + 23
    total = total * 24 + 24
    total = total * 25 + 25
    total = total * 26 + 26
    total = total * 27 + 27
    total = total * 28 + 28
    total = total * 29 + 29
    total = total * 30 + 30
    total = total * 31 + 31
    total = total * 32 + 32
    return total

def aggregate_long_function_25(seed):
    """Split the chained fold into two cohesive helpers (behaviour preserved)."""
    return _aggregate_long_function_25_second(_aggregate_long_function_25_first(seed))
```

### Candidate 1

```python
def _aggregate_long_function_25_first(seed):
    total = seed
    total = total * 1 + 1
    total = total * 2 + 2
    total = total * 3 + 3
    total = total * 4 + 4
    total = total * 5 + 5
    total = total * 6 + 6
    total = total * 7 + 7
    total = total * 8 + 8
    total = total * 9 + 9
    total = total * 10 + 10
    total = total * 11 + 11
    total = total * 12 + 12
    total = total * 13 + 13
    total = total * 14 + 14
    total = total * 15 + 15
    total = total * 16 + 16
    return total

def _aggregate_long_function_25_second(total):
    total = total * 17 + 17
    total = total * 18 + 18
    total = total * 19 + 19
    total = total * 20 + 20
    total = total * 21 + 21
    total = total * 22 + 22
    total = total * 23 + 23
    total = total * 24 + 24
    total = total * 25 + 25
    total = total * 26 + 26
    total = total * 27 + 27
    total = total * 28 + 28
    total = total * 29 + 29
    total = total * 30 + 30
    total = total * 31 + 31
    total = total * 32 + 32
    return total

def aggregate_long_function_25(seed):
    """Split the chained fold into two cohesive helpers (behaviour preserved)."""
    return _aggregate_long_function_25_second(_aggregate_long_function_25_first(seed))
```

### Candidate 2

```python
def _multiply_and_add(seed, multiplier, addend):
    """Helper function to multiply seed by multiplier and add addend."""
    return seed * multiplier + addend

def _aggregate_long_function_25_first(seed):
    total = seed
    for i in range(1, 17):
        total = _multiply_and_add(total, i, i)
    return total

def _aggregate_long_function_25_second(total):
    for i in range(1, 17):
        total = _multiply_and_add(total, i, i)
    return total

def aggregate_long_function_25(seed):
    """Split the chained fold into two cohesive helpers (behaviour preserved)."""
    return _aggregate_long_function_25_second(_aggregate_long_function_25_first(seed))
```

### Candidate 3

```python
def _aggregate_long_function_25_first(seed):
    total = seed
    for i in range(1, 17):
        total *= i + 1
    return total

def _aggregate_long_function_25_second(total):
    for i in range(1, 33):
        total *= i + 1
    return total

def aggregate_long_function_25(seed):
    """Split the chained fold into two cohesive helpers (behaviour preserved)."""
    return _aggregate_long_function_25_second(_aggregate_long_function_25_first(seed))
```

### Candidate 4

```python
def _aggregate_long_function_25_first(seed):
    total = seed
    total = total * 1 + 1
    total = total * 2 + 2
    total = total * 3 + 3
    total = total * 4 + 4
    total = total * 5 + 5
    total = total * 6 + 6
    total = total * 7 + 7
    total = total * 8 + 8
    total = total * 9 + 9
    total = total * 10 + 10
    total = total * 11 + 11
    total = total * 12 + 12
    total = total * 13 + 13
    total = total * 14 + 14
    total = total * 15 + 15
    total = total * 16 + 16
    return total

def _aggregate_long_function_25_second(total):
    total = total * 17 + 17
    total = total * 18 + 18
    total = total * 19 + 19
    total = total * 20 + 20
    total = total * 21 + 21
    total = total * 22 + 22
    total = total * 23 + 23
    total = total * 24 + 24
    total = total * 25 + 25
    total = total * 26 + 26
    total = total * 27 + 27
    total = total * 28 + 28
    total = total * 29 + 29
    total = total * 30 + 30
    total = total * 31 + 31
    total = total * 32 + 32
    return total

def aggregate_long_function_25(seed):
    """Split the chained fold into two cohesive helpers (behaviour preserved)."""
    return _aggregate_long_function_25_second(_aggregate_long_function_25_first(seed))
```

## `long-function-clean-test-02`

Refactoring type: `long-function`

### Original code

```python
def _clean_values_long_function_26(values):
    return [abs(value) for value in values if value is not None]

def _score_first_long_function_26(cleaned):
    total = 0
    total += sum(cleaned) * 2
    total += sum(cleaned) * 3
    total += sum(cleaned) * 4
    total += sum(cleaned) * 5
    total += sum(cleaned) * 6
    total += sum(cleaned) * 7
    total += sum(cleaned) * 8
    total += sum(cleaned) * 9
    total += sum(cleaned) * 10
    total += sum(cleaned) * 11
    total += sum(cleaned) * 12
    total += sum(cleaned) * 13
    total += sum(cleaned) * 14
    total += sum(cleaned) * 15
    total += sum(cleaned) * 16
    return total

def _score_second_long_function_26(cleaned, total):
    total += sum(cleaned) * 17
    total += sum(cleaned) * 18
    total += sum(cleaned) * 19
    total += sum(cleaned) * 20
    total += sum(cleaned) * 21
    total += sum(cleaned) * 22
    total += sum(cleaned) * 23
    total += sum(cleaned) * 24
    total += sum(cleaned) * 25
    total += sum(cleaned) * 26
    total += sum(cleaned) * 27
    total += sum(cleaned) * 28
    total += sum(cleaned) * 29
    total += sum(cleaned) * 30
    total += sum(cleaned) * 31
    total += sum(cleaned) * 32
    total += sum(cleaned) * 33
    return total

def collect_long_function_26(values):
    """Split cleaning and scoring into cohesive helpers (behaviour preserved)."""
    cleaned = _clean_values_long_function_26(values)
    return _score_second_long_function_26(cleaned, _score_first_long_function_26(cleaned))
```

### Candidate 1

```python
def _clean_values_long_function_26(values):
    return [abs(value) for value in values if value is not None]

def _calculate_score(cleaned, multiplier):
    return sum(cleaned) * multiplier

def _score_first_long_function_26(cleaned):
    return _calculate_score(cleaned, 2)

def _score_second_long_function_26(cleaned, total):
    for multiplier in range(3, 34):
        total += _calculate_score(cleaned, multiplier)
    return total

def collect_long_function_26(values):
    """Split cleaning and scoring into cohesive helpers (behaviour preserved)."""
    cleaned = _clean_values_long_function_26(values)
    return _score_second_long_function_26(cleaned, _score_first_long_function_26(cleaned))
```

### Candidate 2

```python
def _clean_values_long_function_26(values):
    return [abs(value) for value in values if value is not None]

def _calculate_total(cleaned, multiplier):
    return sum(cleaned) * multiplier

def _score_first_long_function_26(cleaned):
    return _calculate_total(cleaned, 2)

def _score_second_long_function_26(cleaned, total):
    return _calculate_total(cleaned, 17) + total

def collect_long_function_26(values):
    """Split cleaning and scoring into cohesive helpers (behaviour preserved)."""
    cleaned = _clean_values_long_function_26(values)
    return _score_second_long_function_26(cleaned, _score_first_long_function_26(cleaned))
```

### Candidate 3

```python
def _clean_values_long_function_26(values):
    return [abs(value) for value in values if value is not None]

def _score_first_long_function_26(cleaned):
    total = 0
    total += sum(cleaned) * 2
    total += sum(cleaned) * 3
    total += sum(cleaned) * 4
    total += sum(cleaned) * 5
    total += sum(cleaned) * 6
    total += sum(cleaned) * 7
    total += sum(cleaned) * 8
    total += sum(cleaned) * 9
    total += sum(cleaned) * 10
    total += sum(cleaned) * 11
    total += sum(cleaned) * 12
    total += sum(cleaned) * 13
    total += sum(cleaned) * 14
    total += sum(cleaned) * 15
    total += sum(cleaned) * 16
    return total

def _score_second_long_function_26(cleaned, total):
    total += sum(cleaned) * 17
    total += sum(cleaned) * 18
    total += sum(cleaned) * 19
    total += sum(cleaned) * 20
    total += sum(cleaned) * 21
    total += sum(cleaned) * 22
    total += sum(cleaned) * 23
    total += sum(cleaned) * 24
    total += sum(cleaned) * 25
    total += sum(cleaned) * 26
    total += sum(cleaned) * 27
    total += sum(cleaned) * 28
    total += sum(cleaned) * 29
    total += sum(cleaned) * 30
    total += sum(cleaned) * 31
    total += sum(cleaned) * 32
    total += sum(cleaned) * 33
    return total

def collect_long_function_26(values):
    """Split cleaning and scoring into cohesive helpers (behaviour preserved)."""
    cleaned = _clean_values_long_function_26(values)
    return _score_second_long_function_26(cleaned, _score_first_long_function_26(cleaned))
```

### Candidate 4

```python
def _clean_values_long_function_26(values):
    return [abs(value) for value in values if value is not None]

def _score_first_long_function_26(cleaned):
    total = 0
    total += sum(cleaned) * 2
    total += sum(cleaned) * 3
    total += sum(cleaned) * 4
    total += sum(cleaned) * 5
    total += sum(cleaned) * 6
    total += sum(cleaned) * 7
    total += sum(cleaned) * 8
    total += sum(cleaned) * 9
    total += sum(cleaned) * 10
    total += sum(cleaned) * 11
    total += sum(cleaned) * 12
    total += sum(cleaned) * 13
    total += sum(cleaned) * 14
    total += sum(cleaned) * 15
    total += sum(cleaned) * 16
    return total

def _score_second_long_function_26(cleaned, total):
    total += sum(cleaned) * 17
    total += sum(cleaned) * 18
    total += sum(cleaned) * 19
    total += sum(cleaned) * 20
    total += sum(cleaned) * 21
    total += sum(cleaned) * 22
    total += sum(cleaned) * 23
    total += sum(cleaned) * 24
    total += sum(cleaned) * 25
    total += sum(cleaned) * 26
    total += sum(cleaned) * 27
    total += sum(cleaned) * 28
    total += sum(cleaned) * 29
    total += sum(cleaned) * 30
    total += sum(cleaned) * 31
    total += sum(cleaned) * 32
    total += sum(cleaned) * 33
    return total

def collect_long_function_26(values):
    """Split cleaning and scoring into cohesive helpers (behaviour preserved)."""
    cleaned = _clean_values_long_function_26(values)
    return _score_second_long_function_26(cleaned, _score_first_long_function_26(cleaned))
```

## `long-function-test-01`

Refactoring type: `long-function`

### Original code

```python
def aggregate_long_function_25(seed):
    total_25 = seed
    total_25 = total_25 * 1 + 1
    total_25 = total_25 * 2 + 2
    total_25 = total_25 * 3 + 3
    total_25 = total_25 * 4 + 4
    total_25 = total_25 * 5 + 5
    total_25 = total_25 * 6 + 6
    total_25 = total_25 * 7 + 7
    total_25 = total_25 * 8 + 8
    total_25 = total_25 * 9 + 9
    total_25 = total_25 * 10 + 10
    total_25 = total_25 * 11 + 11
    total_25 = total_25 * 12 + 12
    total_25 = total_25 * 13 + 13
    total_25 = total_25 * 14 + 14
    total_25 = total_25 * 15 + 15
    total_25 = total_25 * 16 + 16
    total_25 = total_25 * 17 + 17
    total_25 = total_25 * 18 + 18
    total_25 = total_25 * 19 + 19
    total_25 = total_25 * 20 + 20
    total_25 = total_25 * 21 + 21
    total_25 = total_25 * 22 + 22
    total_25 = total_25 * 23 + 23
    total_25 = total_25 * 24 + 24
    total_25 = total_25 * 25 + 25
    total_25 = total_25 * 26 + 26
    total_25 = total_25 * 27 + 27
    total_25 = total_25 * 28 + 28
    total_25 = total_25 * 29 + 29
    total_25 = total_25 * 30 + 30
    total_25 = total_25 * 31 + 31
    total_25 = total_25 * 32 + 32
    return total_25
```

### Candidate 1

```python
def aggregate_long_function_25(seed):
    total_25 = seed
    total_25 = total_25 * 1 + 1
    total_25 = total_25 * 2 + 2
    total_25 = total_25 * 3 + 3
    total_25 = total_25 * 4 + 4
    total_25 = total_25 * 5 + 5
    total_25 = total_25 * 6 + 6
    total_25 = total_25 * 7 + 7
    total_25 = total_25 * 8 + 8
    total_25 = total_25 * 9 + 9
    total_25 = total_25 * 10 + 10
    total_25 = total_25 * 11 + 11
    total_25 = total_25 * 12 + 12
    total_25 = total_25 * 13 + 13
    total_25 = total_25 * 14 + 14
    total_25 = total_25 * 15 + 15
    total_25 = total_25 * 16 + 16
    total_25 = total_25 * 17 + 17
    total_25 = total_25 * 18 + 18
    total_25 = total_25 * 19 + 19
    total_25 = total_25 * 20 + 20
    total_25 = total_25 * 21 + 21
    total_25 = total_25 * 22 + 22
    total_25 = total_25 * 23 + 23
    total_25 = total_25 * 24 + 24
    total_25 = total_25 * 25 + 25
    total_25 = total_25 * 26 + 26
    total_25 = total_25 * 27 + 27
    total_25 = total_25 * 28 + 28
    total_25 = total_25 * 29 + 29
    total_25 = total_25 * 30 + 30
    total_25 = total_25 * 31 + 31
    total_25 = total_25 * 32 + 32
    return total_25
```

### Candidate 2

```python
def _aggregate_first_long_function_25(seed):
    total = seed
    total = total * 1 + 1
    total = total * 2 + 2
    total = total * 3 + 3
    total = total * 4 + 4
    total = total * 5 + 5
    total = total * 6 + 6
    total = total * 7 + 7
    total = total * 8 + 8
    total = total * 9 + 9
    total = total * 10 + 10
    total = total * 11 + 11
    total = total * 12 + 12
    total = total * 13 + 13
    total = total * 14 + 14
    total = total * 15 + 15
    total = total * 16 + 16
    return total

def _aggregate_second_long_function_25(total):
    total = total * 17 + 17
    total = total * 18 + 18
    total = total * 19 + 19
    total = total * 20 + 20
    total = total * 21 + 21
    total = total * 22 + 22
    total = total * 23 + 23
    total = total * 24 + 24
    total = total * 25 + 25
    total = total * 26 + 26
    total = total * 27 + 27
    total = total * 28 + 28
    total = total * 29 + 29
    total = total * 30 + 30
    total = total * 31 + 31
    total = total * 32 + 32
    return total

def aggregate_long_function_25(seed):
    """Split the chained fold into two cohesive helpers (behaviour preserved)."""
    return _aggregate_second_long_function_25(_aggregate_first_long_function_25(seed))
```

### Candidate 3

```python
def aggregate_long_function_25(seed):
    return sum((i + 1) * seed for i in range(1, 32))
```

### Candidate 4

```python
def aggregate_long_function_25(seed):
    return seed * sum(range(1, 33))
```

## `long-function-test-02`

Refactoring type: `long-function`

### Original code

```python
def collect_long_function_26(values):
    cleaned = [abs(value) for value in values if value is not None]
    total = 0
    total += sum(cleaned) * 2
    total += sum(cleaned) * 3
    total += sum(cleaned) * 4
    total += sum(cleaned) * 5
    total += sum(cleaned) * 6
    total += sum(cleaned) * 7
    total += sum(cleaned) * 8
    total += sum(cleaned) * 9
    total += sum(cleaned) * 10
    total += sum(cleaned) * 11
    total += sum(cleaned) * 12
    total += sum(cleaned) * 13
    total += sum(cleaned) * 14
    total += sum(cleaned) * 15
    total += sum(cleaned) * 16
    total += sum(cleaned) * 17
    total += sum(cleaned) * 18
    total += sum(cleaned) * 19
    total += sum(cleaned) * 20
    total += sum(cleaned) * 21
    total += sum(cleaned) * 22
    total += sum(cleaned) * 23
    total += sum(cleaned) * 24
    total += sum(cleaned) * 25
    total += sum(cleaned) * 26
    total += sum(cleaned) * 27
    total += sum(cleaned) * 28
    total += sum(cleaned) * 29
    total += sum(cleaned) * 30
    total += sum(cleaned) * 31
    total += sum(cleaned) * 32
    total += sum(cleaned) * 33
    return total
```

### Candidate 1

```python
from typing import List

def collect_long_function_26(values: List[float]) -> float:
    cleaned = [abs(value) for value in values if value is not None]
    return sum(cleaned) * sum(range(1, 34))
```

### Candidate 2

```python
def _clean_values_long_function_26(values):
    return [abs(value) for value in values if value is not None]

def _score_first_long_function_26(cleaned):
    total = 0
    total += sum(cleaned) * 2
    total += sum(cleaned) * 3
    total += sum(cleaned) * 4
    total += sum(cleaned) * 5
    total += sum(cleaned) * 6
    total += sum(cleaned) * 7
    total += sum(cleaned) * 8
    total += sum(cleaned) * 9
    total += sum(cleaned) * 10
    total += sum(cleaned) * 11
    total += sum(cleaned) * 12
    total += sum(cleaned) * 13
    total += sum(cleaned) * 14
    total += sum(cleaned) * 15
    total += sum(cleaned) * 16
    return total

def _score_second_long_function_26(cleaned, total):
    total += sum(cleaned) * 17
    total += sum(cleaned) * 18
    total += sum(cleaned) * 19
    total += sum(cleaned) * 20
    total += sum(cleaned) * 21
    total += sum(cleaned) * 22
    total += sum(cleaned) * 23
    total += sum(cleaned) * 24
    total += sum(cleaned) * 25
    total += sum(cleaned) * 26
    total += sum(cleaned) * 27
    total += sum(cleaned) * 28
    total += sum(cleaned) * 29
    total += sum(cleaned) * 30
    total += sum(cleaned) * 31
    total += sum(cleaned) * 32
    total += sum(cleaned) * 33
    return total

def collect_long_function_26(values):
    """Split cleaning and scoring into two cohesive helpers (behaviour preserved)."""
    cleaned = _clean_values_long_function_26(values)
    return _score_second_long_function_26(cleaned, _score_first_long_function_26(cleaned))
```

### Candidate 3

```python
def collect_long_function_26(values):
    cleaned = [abs(value) for value in values if value is not None]
    total = sum(cleaned)
    return total * (total + 1) * 31 // 2
```

### Candidate 4

```python
def collect_long_function_26(values):
    cleaned = [abs(value) for value in values if value is not None]
    total = 0
    total += sum(cleaned) * 2
    total += sum(cleaned) * 3
    total += sum(cleaned) * 4
    total += sum(cleaned) * 5
    total += sum(cleaned) * 6
    total += sum(cleaned) * 7
    total += sum(cleaned) * 8
    total += sum(cleaned) * 9
    total += sum(cleaned) * 10
    total += sum(cleaned) * 11
    total += sum(cleaned) * 12
    total += sum(cleaned) * 13
    total += sum(cleaned) * 14
    total += sum(cleaned) * 15
    total += sum(cleaned) * 16
    total += sum(cleaned) * 17
    total += sum(cleaned) * 18
    total += sum(cleaned) * 19
    total += sum(cleaned) * 20
    total += sum(cleaned) * 21
    total += sum(cleaned) * 22
    total += sum(cleaned) * 23
    total += sum(cleaned) * 24
    total += sum(cleaned) * 25
    total += sum(cleaned) * 26
    total += sum(cleaned) * 27
    total += sum(cleaned) * 28
    total += sum(cleaned) * 29
    total += sum(cleaned) * 30
    total += sum(cleaned) * 31
    total += sum(cleaned) * 32
    total += sum(cleaned) * 33
    return total
```

## `long-function-test-03`

Refactoring type: `long-function`

### Original code

```python
def aggregate_long_function_27(seed):
    total_27 = seed
    total_27 = total_27 * 1 + 1
    total_27 = total_27 * 2 + 2
    total_27 = total_27 * 3 + 3
    total_27 = total_27 * 4 + 4
    total_27 = total_27 * 5 + 5
    total_27 = total_27 * 6 + 6
    total_27 = total_27 * 7 + 7
    total_27 = total_27 * 8 + 8
    total_27 = total_27 * 9 + 9
    total_27 = total_27 * 10 + 10
    total_27 = total_27 * 11 + 11
    total_27 = total_27 * 12 + 12
    total_27 = total_27 * 13 + 13
    total_27 = total_27 * 14 + 14
    total_27 = total_27 * 15 + 15
    total_27 = total_27 * 16 + 16
    total_27 = total_27 * 17 + 17
    total_27 = total_27 * 18 + 18
    total_27 = total_27 * 19 + 19
    total_27 = total_27 * 20 + 20
    total_27 = total_27 * 21 + 21
    total_27 = total_27 * 22 + 22
    total_27 = total_27 * 23 + 23
    total_27 = total_27 * 24 + 24
    total_27 = total_27 * 25 + 25
    total_27 = total_27 * 26 + 26
    total_27 = total_27 * 27 + 27
    total_27 = total_27 * 28 + 28
    total_27 = total_27 * 29 + 29
    total_27 = total_27 * 30 + 30
    total_27 = total_27 * 31 + 31
    total_27 = total_27 * 32 + 32
    return total_27
```

### Candidate 1

```python
def aggregate_long_function_27(seed):
    total_27 = seed
    for i in range(1, 33):
        total_27 *= i + 1
    return total_27
```

### Candidate 2

```python
def aggregate_long_function_27(seed):
    total_27 = seed
    for i in range(1, 33):
        total_27 *= i + 1
    return total_27
```

### Candidate 3

```python
def aggregate_long_function_27(seed):
    total_27 = seed
    total_27 = total_27 * 1 + 1
    total_27 = total_27 * 2 + 2
    total_27 = total_27 * 3 + 3
    total_27 = total_27 * 4 + 4
    total_27 = total_27 * 5 + 5
    total_27 = total_27 * 6 + 6
    total_27 = total_27 * 7 + 7
    total_27 = total_27 * 8 + 8
    total_27 = total_27 * 9 + 9
    total_27 = total_27 * 10 + 10
    total_27 = total_27 * 11 + 11
    total_27 = total_27 * 12 + 12
    total_27 = total_27 * 13 + 13
    total_27 = total_27 * 14 + 14
    total_27 = total_27 * 15 + 15
    total_27 = total_27 * 16 + 16
    total_27 = total_27 * 17 + 17
    total_27 = total_27 * 18 + 18
    total_27 = total_27 * 19 + 19
    total_27 = total_27 * 20 + 20
    total_27 = total_27 * 21 + 21
    total_27 = total_27 * 22 + 22
    total_27 = total_27 * 23 + 23
    total_27 = total_27 * 24 + 24
    total_27 = total_27 * 25 + 25
    total_27 = total_27 * 26 + 26
    total_27 = total_27 * 27 + 27
    total_27 = total_27 * 28 + 28
    total_27 = total_27 * 29 + 29
    total_27 = total_27 * 30 + 30
    total_27 = total_27 * 31 + 31
    total_27 = total_27 * 32 + 32
    return total_27
```

### Candidate 4

```python
def _aggregate_long_function_first(seed):
    total = seed
    total = total * 1 + 1
    total = total * 2 + 2
    total = total * 3 + 3
    total = total * 4 + 4
    total = total * 5 + 5
    total = total * 6 + 6
    total = total * 7 + 7
    total = total * 8 + 8
    total = total * 9 + 9
    total = total * 10 + 10
    total = total * 11 + 11
    total = total * 12 + 12
    total = total * 13 + 13
    total = total * 14 + 14
    total = total * 15 + 15
    total = total * 16 + 16
    return total

def _aggregate_long_function_second(total):
    total = total * 17 + 17
    total = total * 18 + 18
    total = total * 19 + 19
    total = total * 20 + 20
    total = total * 21 + 21
    total = total * 22 + 22
    total = total * 23 + 23
    total = total * 24 + 24
    total = total * 25 + 25
    total = total * 26 + 26
    total = total * 27 + 27
    total = total * 28 + 28
    total = total * 29 + 29
    total = total * 30 + 30
    total = total * 31 + 31
    total = total * 32 + 32
    return total

def aggregate_long_function_27(seed):
    """Split the chained fold into two cohesive helpers (behaviour preserved)."""
    return _aggregate_long_function_second(_aggregate_long_function_first(seed))
```

## `long-function-test-04`

Refactoring type: `long-function`

### Original code

```python
def collect_long_function_28(values):
    cleaned = [abs(value) for value in values if value is not None]
    total = 0
    total += sum(cleaned) * 2
    total += sum(cleaned) * 3
    total += sum(cleaned) * 4
    total += sum(cleaned) * 5
    total += sum(cleaned) * 6
    total += sum(cleaned) * 7
    total += sum(cleaned) * 8
    total += sum(cleaned) * 9
    total += sum(cleaned) * 10
    total += sum(cleaned) * 11
    total += sum(cleaned) * 12
    total += sum(cleaned) * 13
    total += sum(cleaned) * 14
    total += sum(cleaned) * 15
    total += sum(cleaned) * 16
    total += sum(cleaned) * 17
    total += sum(cleaned) * 18
    total += sum(cleaned) * 19
    total += sum(cleaned) * 20
    total += sum(cleaned) * 21
    total += sum(cleaned) * 22
    total += sum(cleaned) * 23
    total += sum(cleaned) * 24
    total += sum(cleaned) * 25
    total += sum(cleaned) * 26
    total += sum(cleaned) * 27
    total += sum(cleaned) * 28
    total += sum(cleaned) * 29
    total += sum(cleaned) * 30
    total += sum(cleaned) * 31
    total += sum(cleaned) * 32
    total += sum(cleaned) * 33
    return total
```

### Candidate 1

```python
def collect_long_function_28(values):
    cleaned = [abs(value) for value in values if value is not None]
    return sum(cleaned) * sum(range(1, 34))
```

### Candidate 2

```python
def collect_long_function_28(values):
    cleaned = [abs(value) for value in values if value is not None]
    total = 0
    total += sum(cleaned) * 2
    total += sum(cleaned) * 3
    total += sum(cleaned) * 4
    total += sum(cleaned) * 5
    total += sum(cleaned) * 6
    total += sum(cleaned) * 7
    total += sum(cleaned) * 8
    total += sum(cleaned) * 9
    total += sum(cleaned) * 10
    total += sum(cleaned) * 11
    total += sum(cleaned) * 12
    total += sum(cleaned) * 13
    total += sum(cleaned) * 14
    total += sum(cleaned) * 15
    total += sum(cleaned) * 16
    total += sum(cleaned) * 17
    total += sum(cleaned) * 18
    total += sum(cleaned) * 19
    total += sum(cleaned) * 20
    total += sum(cleaned) * 21
    total += sum(cleaned) * 22
    total += sum(cleaned) * 23
    total += sum(cleaned) * 24
    total += sum(cleaned) * 25
    total += sum(cleaned) * 26
    total += sum(cleaned) * 27
    total += sum(cleaned) * 28
    total += sum(cleaned) * 29
    total += sum(cleaned) * 30
    total += sum(cleaned) * 31
    total += sum(cleaned) * 32
    total += sum(cleaned) * 33
    return total
```

### Candidate 3

```python
def _clean_values_long_function_28(values):
    """Extract positive values and discard nones."""
    return [abs(value) for value in values if value is not None]

def _score_positive_long_function_28(cleaned):
    """Score positive values according to their position in the list."""
    total = 0
    total += sum(cleaned) * 2
    total += sum(cleaned) * 3
    total += sum(cleaned) * 4
    total += sum(cleaned) * 5
    total += sum(cleaned) * 6
    total += sum(cleaned) * 7
    total += sum(cleaned) * 8
    total += sum(cleaned) * 9
    total += sum(cleaned) * 10
    total += sum(cleaned) * 11
    total += sum(cleaned) * 12
    total += sum(cleaned) * 13
    total += sum(cleaned) * 14
    total += sum(cleaned) * 15
    total += sum(cleaned) * 16
    return total

def _score_negative_long_function_28(cleaned):
    """Score negative values according to their position in the list."""
    total = 0
    total += sum(cleaned) * 17
    total += sum(cleaned) * 18
    total += sum(cleaned) * 19
    total += sum(cleaned) * 20
    total += sum(cleaned) * 21
    total += sum(cleaned) * 22
    total += sum(cleaned) * 23
    total += sum(cleaned) * 24
    total += sum(cleaned) * 25
    total += sum(cleaned) * 26
    total += sum(cleaned) * 27
    total += sum(cleaned) * 28
    total += sum(cleaned) * 29
    total += sum(cleaned) * 30
    total += sum(cleaned) * 31
    total += sum(cleaned) * 32
    total += sum(cleaned) * 33
    return total

def collect_long_function_28(values):
    """Split cleaning and scoring into two cohesive helpers (behaviour preserved)."""
    cleaned = _clean_values_long_function_28(values)
    return _score_positive_long_function_28(cleaned) + _score_negative_long_function_28(cleaned)
```

### Candidate 4

```python
from typing import List, Optional

def collect_long_function_28(values: List[Optional[float]]) -> float:
    cleaned = [abs(value) for value in values if value is not None]
    return sum(cleaned) * sum(range(1, 34))
```

## `long-parameter-list-clean-test-01`

Refactoring type: `long-parameter-list`

### Original code

```python
from dataclasses import dataclass


@dataclass
class ReportRequest_long_parameter_list_25:
    title: str
    author: str
    date: str
    category: str
    priority: int
    tags: list


def create_report_long_parameter_list_25(request: ReportRequest_long_parameter_list_25):
    """Build the payload from one cohesive request object."""
    return {
        'title': request.title,
        'author': request.author,
        'date': request.date,
        'category': request.category,
        'priority': request.priority,
        'tags': request.tags,
    }
```

### Candidate 1

```python
from dataclasses import dataclass


@dataclass
class ReportRequest_long_parameter_list_25:
    title: str
    author: str
    date: str
    category: str
    priority: int
    tags: list


def create_report_long_parameter_list_25(request: ReportRequest_long_parameter_list_25):
    """Build the payload from one cohesive request object."""
    return {
        'title': request.title,
        'author': request.author,
        'date': request.date,
        'category': request.category,
        'priority': request.priority,
        'tags': request.tags,
    }
```

### Candidate 2

```python
from dataclasses import dataclass


@dataclass
class ReportRequest_long_parameter_list_25:
    title: str
    author: str
    date: str
    category: str
    priority: int
    tags: list


def create_report_long_parameter_list_25(request: ReportRequest_long_parameter_list_25):
    """Build the payload from one cohesive request object."""
    return {
        'title': request.title,
        'author': request.author,
        'date': request.date,
        'category': request.category,
        'priority': request.priority,
        'tags': request.tags,
    }
```

### Candidate 3

```python
from dataclasses import dataclass


@dataclass
class ReportRequest_long_parameter_list_25:
    title: str
    author: str
    date: str
    category: str
    priority: int
    tags: list


def create_report_long_parameter_list_25(request: ReportRequest_long_parameter_list_25):
    """Build the payload from one cohesive request object."""
    return {
        'title': request.title,
        'author': request.author,
        'date': request.date,
        'category': request.category,
        'priority': request.priority,
        'tags': request.tags,
    }
```

### Candidate 4

```python
from dataclasses import dataclass


@dataclass
class ReportRequest_long_parameter_list_25:
    title: str
    author: str
    date: str
    category: str
    priority: int
    tags: list


def create_report_long_parameter_list_25(request: ReportRequest_long_parameter_list_25):
    """Build the payload from one cohesive request object."""
    payload = {}
    payload['title'] = request.title
    payload['author'] = request.author
    payload['date'] = request.date
    payload['category'] = request.category
    payload['priority'] = request.priority
    payload['tags'] = request.tags
    return payload
```

## `long-parameter-list-clean-test-02`

Refactoring type: `long-parameter-list`

### Original code

```python
from dataclasses import dataclass


@dataclass
class ProfileRequest_long_parameter_list_26:
    username: str
    email: str
    age: int
    country: str
    plan: str
    active: bool


def build_profile_long_parameter_list_26(request: ProfileRequest_long_parameter_list_26):
    """Build the payload from one cohesive request object."""
    return {
        'username': request.username,
        'email': request.email,
        'age': request.age,
        'country': request.country,
        'plan': request.plan,
        'active': request.active,
    }
```

### Candidate 1

```python
from dataclasses import dataclass


@dataclass
class ProfileRequest_long_parameter_list_26:
    username: str
    email: str
    age: int
    country: str
    plan: str
    active: bool

def build_profile_long_parameter_list_26(request: ProfileRequest_long_parameter_list_26):
    """Build the payload from one cohesive request object."""
    payload = {}
    payload['username'] = request.username
    payload['email'] = request.email
    payload['age'] = request.age
    payload['country'] = request.country
    payload['plan'] = request.plan
    payload['active'] = request.active
    return payload
```

### Candidate 2

```python
from dataclasses import dataclass


@dataclass
class ProfileRequest_long_parameter_list_26:
    username: str
    email: str
    age: int
    country: str
    plan: str
    active: bool


def build_profile_long_parameter_list_26(request: ProfileRequest_long_parameter_list_26):
    """Build the payload from one cohesive request object."""
    return {
        'username': request.username,
        'email': request.email,
        'age': request.age,
        'country': request.country,
        'plan': request.plan,
        'active': request.active,
    }
```

### Candidate 3

```python
from dataclasses import dataclass


@dataclass
class ProfileRequest_long_parameter_list_26:
    username: str
    email: str
    age: int
    country: str
    plan: str
    active: bool

def build_profile_long_parameter_list_26(request: ProfileRequest_long_parameter_list_26):
    """Build the payload from one cohesive request object."""
    payload = {}
    payload['username'] = request.username
    payload['email'] = request.email
    payload['age'] = request.age
    payload['country'] = request.country
    payload['plan'] = request.plan
    payload['active'] = request.active
    return payload
```

### Candidate 4

```python
from dataclasses import dataclass


@dataclass
class ProfileRequest_long_parameter_list_26:
    username: str
    email: str
    age: int
    country: str
    plan: str
    active: bool


def build_profile_long_parameter_list_26(request: ProfileRequest_long_parameter_list_26):
    """Build the payload from one cohesive request object."""
    return {
        'username': request.username,
        'email': request.email,
        'age': request.age,
        'country': request.country,
        'plan': request.plan,
        'active': request.active,
    }
```

## `long-parameter-list-test-01`

Refactoring type: `long-parameter-list`

### Original code

```python
def create_report_long_parameter_list_25(title, author, date, category, priority, tags):
    return {
        'title': title,
        'author': author,
        'date': date,
        'category': category,
        'priority': priority,
        'tags': tags,
    }
```

### Candidate 1

```python
def create_report_long_parameter_list_25(report_data):
    return report_data

def create_report_with_parameters(title, author, date, category, priority, tags):
    report_data = {
        'title': title,
        'author': author,
        'date': date,
        'category': category,
        'priority': priority,
        'tags': tags,
    }
    return create_report_long_parameter_list_25(report_data)
```

### Candidate 2

```python
class ReportData:
    def __init__(self, title, author, date, category, priority, tags):
        self.title = title
        self.author = author
        self.date = date
        self.category = category
        self.priority = priority
        self.tags = tags

def create_report_long_parameter_list_25(report_data):
    return report_data.__dict__
```

### Candidate 3

```python
def create_report_long_parameter_list_25(title, author, date, category, priority, tags):
    return {
        'title': title,
        'author': author,
        'date': date,
        'category': category,
        'priority': priority,
        'tags': tags,
    }
```

### Candidate 4

```python
from dataclasses import dataclass


@dataclass
class ReportRequest_long_parameter_list_25:
    title: str
    author: str
    date: str
    category: str
    priority: int
    tags: list


def create_report_long_parameter_list_25(request: ReportRequest_long_parameter_list_25):
    """Build the payload from one cohesive request object."""
    return {
        'title': request.title,
        'author': request.author,
        'date': request.date,
        'category': request.category,
        'priority': request.priority,
        'tags': request.tags,
    }
```

## `long-parameter-list-test-02`

Refactoring type: `long-parameter-list`

### Original code

```python
def build_profile_long_parameter_list_26(username, email, age, country, plan, active):
    return {
        'username': username,
        'email': email,
        'age': age,
        'country': country,
        'plan': plan,
        'active': active,
    }
```

### Candidate 1

```python
def build_profile_long_parameter_list_26(username, email, age, country, plan, active):
    return {
        'username': username,
        'email': email,
        'age': age,
        'country': country,
        'plan': plan,
        'active': active,
    }
```

### Candidate 2

```python
class ProfileBuilder:
    def __init__(self, username, email, age, country, plan, active):
        self.username = username
        self.email = email
        self.age = age
        self.country = country
        self.plan = plan
        self.active = active

def build_profile_long_parameter_list_26(profile_builder):
    return {
        'username': profile_builder.username,
        'email': profile_builder.email,
        'age': profile_builder.age,
        'country': profile_builder.country,
        'plan': profile_builder.plan,
        'active': profile_builder.active,
    }
```

### Candidate 3

```python
from dataclasses import dataclass


@dataclass
class ProfileRequest_long_parameter_list_26:
    username: str
    email: str
    age: int
    country: str
    plan: str
    active: bool


def build_profile_long_parameter_list_26(request: ProfileRequest_long_parameter_list_26):
    """Build the payload from one cohesive request object."""
    return {
        'username': request.username,
        'email': request.email,
        'age': request.age,
        'country': request.country,
        'plan': request.plan,
        'active': request.active,
    }
```

### Candidate 4

```python
class ProfileBuilder:
    def __init__(self, username, email, age, country, plan, active):
        self.username = username
        self.email = email
        self.age = age
        self.country = country
        self.plan = plan
        self.active = active

    def build_profile(self):
        return {
            'username': self.username,
            'email': self.email,
            'age': self.age,
            'country': self.country,
            'plan': self.plan,
            'active': self.active,
        }

def build_profile_long_parameter_list_26(username, email, age, country, plan, active):
    builder = ProfileBuilder(username, email, age, country, plan, active)
    return builder.build_profile()
```

## `long-parameter-list-test-03`

Refactoring type: `long-parameter-list`

### Original code

```python
def make_order_long_parameter_list_27(order_id, customer, item, quantity, price, currency):
    return {
        'order_id': order_id,
        'customer': customer,
        'item': item,
        'quantity': quantity,
        'price': price,
        'currency': currency,
    }
```

### Candidate 1

```python
class Order:
    def __init__(self, order_id, customer, item, quantity, price, currency):
        self.order_id = order_id
        self.customer = customer
        self.item = item
        self.quantity = quantity
        self.price = price
        self.currency = currency

def make_order_long_parameter_list_27(order_id, customer, item, quantity, price, currency):
    return Order(order_id, customer, item, quantity, price, currency)
```

### Candidate 2

```python
class OrderData:
    def __init__(self, order_id, customer, item, quantity, price, currency):
        self.order_id = order_id
        self.customer = customer
        self.item = item
        self.quantity = quantity
        self.price = price
        self.currency = currency

def make_order_with_data(order_data):
    return {
        'order_id': order_data.order_id,
        'customer': order_data.customer,
        'item': order_data.item,
        'quantity': order_data.quantity,
        'price': order_data.price,
        'currency': order_data.currency,
    }

def make_order_long_parameter_list_27(order_id, customer, item, quantity, price, currency):
    return make_order_with_data(OrderData(order_id, customer, item, quantity, price, currency))
```

### Candidate 3

```python
def make_order_long_parameter_list_27(order_id, customer, item, quantity, price, currency):
    return {
        'order_id': order_id,
        'customer': customer,
        'item': item,
        'quantity': quantity,
        'price': price,
        'currency': currency,
    }
```

### Candidate 4

```python
from dataclasses import dataclass


@dataclass
class OrderRequest_long_parameter_list_27:
    order_id: int
    customer: str
    item: str
    quantity: int
    price: float
    currency: str


def make_order_long_parameter_list_27(request: OrderRequest_long_parameter_list_27):
    """Build the payload from one cohesive request object."""
    return {
        'order_id': request.order_id,
        'customer': request.customer,
        'item': request.item,
        'quantity': request.quantity,
        'price': request.price,
        'currency': request.currency,
    }
```

## `long-parameter-list-test-04`

Refactoring type: `long-parameter-list`

### Original code

```python
def create_report_long_parameter_list_28(title, author, date, category, priority, tags):
    return {
        'title': title,
        'author': author,
        'date': date,
        'category': category,
        'priority': priority,
        'tags': tags,
    }
```

### Candidate 1

```python
class ReportParameters:
    def __init__(self, title, author, date, category, priority, tags):
        self.title = title
        self.author = author
        self.date = date
        self.category = category
        self.priority = priority
        self.tags = tags

def create_report_with_params(params):
    return {
        'title': params.title,
        'author': params.author,
        'date': params.date,
        'category': params.category,
        'priority': params.priority,
        'tags': params.tags,
    }

def create_report_long_parameter_list_28(title, author, date, category, priority, tags):
    params = ReportParameters(title, author, date, category, priority, tags)
    return create_report_with_params(params)
```

### Candidate 2

```python
def create_report_long_parameter_list_28(title, author, date, category, priority, tags):
    return {
        'title': title,
        'author': author,
        'date': date,
        'category': category,
        'priority': priority,
        'tags': tags,
    }
```

### Candidate 3

```python
def create_report_long_parameter_list_28(report_data):
    return report_data

def create_report_long_parameter_list_28(title, author, date, category, priority, tags):
    report_data = {
        'title': title,
        'author': author,
        'date': date,
        'category': category,
        'priority': priority,
        'tags': tags,
    }
    return create_report_long_parameter_list_28(report_data)
```

### Candidate 4

```python
from dataclasses import dataclass


@dataclass
class ReportRequest_long_parameter_list_28:
    title: str
    author: str
    date: str
    category: str
    priority: int
    tags: list


def create_report_long_parameter_list_28(request: ReportRequest_long_parameter_list_28):
    """Build the payload from a cohesive request object."""
    return {
        'title': request.title,
        'author': request.author,
        'date': request.date,
        'category': request.category,
        'priority': request.priority,
        'tags': request.tags,
    }
```

## `mutable-default-arg-clean-test-01`

Refactoring type: `mutable-default-arg`

### Original code

```python
def tag_mutable_default_arg_25(name, labels=None):
    if labels is None:
        labels = []
    labels.append(name)
    return labels
```

### Candidate 1

```python
def tag_mutable_default_arg_25(name, labels=None):
    if labels is None:
        labels = []
    labels.append(name)
    return labels
```

### Candidate 2

```python
def tag_mutable_default_arg_25(name, labels=[]):
    labels.append(name)
    return labels
```

### Candidate 3

```python
def tag_mutable_default_arg_25(name, labels=None):
    if labels is None:
        labels = []
    labels.append(name)
    return labels
```

### Candidate 4

```python
def tag_mutable_default_arg_25(name, labels=()):
    labels += (name,)
    return labels
```

## `mutable-default-arg-clean-test-02`

Refactoring type: `mutable-default-arg`

### Original code

```python
def register_mutable_default_arg_26(name, cache=None):
    if cache is None:
        cache = {}
    cache[name] = cache.get(name, 0) + 1
    return cache
```

### Candidate 1

```python
def register_mutable_default_arg_26(name, cache=None):
    if cache is None:
        cache = {}
    cache[name] = cache.get(name, 0) + 1
    return cache
```

### Candidate 2

```python
def register_mutable_default_arg_26(name, cache=None):
    if cache is None:
        cache = {}
    cache[name] = cache.get(name, 0) + 1
    return cache
```

### Candidate 3

```python
def register_mutable_default_arg_26(name, cache=None):
    if cache is None:
        cache = {}
    cache[name] = cache.get(name, 0) + 1
    return cache
```

### Candidate 4

```python
def register_mutable_default_arg_26(name, cache=None):
    if cache is None:
        cache = {}
    cache[name] = cache.get(name, 0) + 1
    return cache
```

## `mutable-default-arg-test-01`

Refactoring type: `mutable-default-arg`

### Original code

```python
def tag_mutable_default_arg_25(name, labels=[]):
    labels.append(name)
    return labels
```

### Candidate 1

```python
def tag_mutable_default_arg_25(name, labels=None):
    if labels is None:
        labels = []
    labels.append(name)
    return labels
```

### Candidate 2

```python
def tag_mutable_default_arg_25(name, labels=None):
    if labels is None:
        labels = []
    labels.append(name)
    return labels
```

### Candidate 3

```python
def tag_mutable_default_arg_25(name, labels=None):
    if labels is None:
        labels = []
    labels.append(name)
    return labels
```

### Candidate 4

```python
def tag_mutable_default_arg_25(name, labels=None):
    if labels is None:
        labels = []
    labels.append(name)
    return labels
```

## `mutable-default-arg-test-02`

Refactoring type: `mutable-default-arg`

### Original code

```python
def register_mutable_default_arg_26(name, cache={}):
    cache[name] = cache.get(name, 0) + 1
    return cache
```

### Candidate 1

```python
def register_mutable_default_arg_26(name, cache=None):
    if cache is None:
        cache = {}
    cache[name] = cache.get(name, 0) + 1
    return cache
```

### Candidate 2

```python
def register_mutable_default_arg_26(name, cache=None):
    if cache is None:
        cache = {}
    cache[name] = cache.get(name, 0) + 1
    return cache
```

### Candidate 3

```python
def register_mutable_default_arg_26(name, cache=None):
    if cache is None:
        cache = {}
    cache[name] = cache.get(name, 0) + 1
    return cache
```

### Candidate 4

```python
def register_mutable_default_arg_26(name, cache=None):
    if cache is None:
        cache = {}
    cache[name] = cache.get(name, 0) + 1
    return cache
```

## `mutable-default-arg-test-03`

Refactoring type: `mutable-default-arg`

### Original code

```python
def track_mutable_default_arg_27(name, seen=set()):
    seen.add(name)
    return len(seen)
```

### Candidate 1

```python
def track_mutable_default_arg_27(name, seen=None):
    if seen is None:
        seen = set()
    seen.add(name)
    return len(seen)
```

### Candidate 2

```python
def track_mutable_default_arg_27(name, seen=None):
    if seen is None:
        seen = set()
    seen.add(name)
    return len(seen)
```

### Candidate 3

```python
def track_mutable_default_arg_27(name, seen=None):
    if seen is None:
        seen = set()
    seen.add(name)
    return len(seen)
```

### Candidate 4

```python
def track_mutable_default_arg_27(name, seen=None):
    if seen is None:
        seen = set()
    seen.add(name)
    return len(seen)
```

## `mutable-default-arg-test-04`

Refactoring type: `mutable-default-arg`

### Original code

```python
def tag_mutable_default_arg_28(name, labels=[]):
    labels.append(name)
    return labels
```

### Candidate 1

```python
def tag_mutable_default_arg_28(name, labels=None):
    if labels is None:
        labels = []
    labels.append(name)
    return labels
```

### Candidate 2

```python
def tag_mutable_default_arg_28(name, labels=None):
    if labels is None:
        labels = []
    labels.append(name)
    return labels
```

### Candidate 3

```python
def tag_mutable_default_arg_28(name, labels=None):
    if labels is None:
        labels = []
    labels.append(name)
    return labels
```

### Candidate 4

```python
def tag_mutable_default_arg_28(name, labels=None):
    if labels is None:
        labels = []
    labels.append(name)
    return labels
```

_Generated at 2026-11-10T22:07:53Z from 48 blinded cases. Scores are recorded only by the human raters in `score_sheet.csv`._
