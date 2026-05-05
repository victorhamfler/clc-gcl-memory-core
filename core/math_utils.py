from __future__ import annotations

import math


EPS = 1e-12


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def sigmoid(value: float) -> float:
    if value >= 0:
        z = math.exp(-value)
        return 1.0 / (1.0 + z)
    z = math.exp(value)
    return z / (1.0 + z)


def norm(vec: list[float]) -> float:
    return math.sqrt(sum(float(x) * float(x) for x in vec))


def normalize(vec: list[float]) -> list[float]:
    n = norm(vec)
    if n <= EPS:
        return [0.0 for _ in vec]
    return [float(x) / n for x in vec]


def dot(a: list[float], b: list[float]) -> float:
    return sum(float(x) * float(y) for x, y in zip(a, b))


def cosine(a: list[float], b: list[float]) -> float:
    na = norm(a)
    nb = norm(b)
    if na <= EPS or nb <= EPS:
        return 0.0
    return dot(a, b) / (na * nb)


def euclidean(a: list[float], b: list[float]) -> float:
    return math.sqrt(sum((float(x) - float(y)) ** 2 for x, y in zip(a, b)))


def weighted_average(old: list[float], new: list[float], rate: float) -> list[float]:
    r = clamp(rate)
    return [(1.0 - r) * float(x) + r * float(y) for x, y in zip(old, new)]


def effective_dimension_from_vectors(vectors: list[list[float]]) -> float:
    if not vectors:
        return 1.0
    dim = len(vectors[0])
    if dim == 0:
        return 1.0
    means = [0.0] * dim
    for vec in vectors:
        for i, value in enumerate(vec):
            means[i] += float(value)
    means = [x / len(vectors) for x in means]
    variances = [0.0] * dim
    for vec in vectors:
        for i, value in enumerate(vec):
            diff = float(value) - means[i]
            variances[i] += diff * diff
    variances = [max(0.0, x / max(1, len(vectors) - 1)) for x in variances]
    total = sum(variances)
    if total <= EPS:
        return 1.0
    denom = sum(v * v for v in variances) + EPS
    return max(1.0, (total * total) / denom)
